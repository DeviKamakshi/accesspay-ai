import uuid
import re
import json
from typing import Optional, Dict, Any, List, Tuple
from app.models.purchase import PurchaseState, PurchaseReview, PurchaseResponse, ConfirmationEvent
from app.models.analytics import OrderLineItem
from app.services.cart_service import cart_service
from app.services.accessibility_service import accessibility_service
from app.db.database import db

AMBIGUOUS_PHRASES = [
    "that looks good",
    "that one looks good",
    "looks good",
    "i like that",
    "i want that",
    "get that",
    "get it",
    "choose that",
    "take that",
    "yes",
    "yeah",
    "yep",
    "sure",
    "okay",
    "ok",
    "go ahead",
    "do it",
    "buy it",
    "order it"
]


class ConfirmationService:
    def __init__(self):
        self._state = PurchaseState.BROWSING
        self._active_review: Optional[PurchaseReview] = None
        self._is_processing = False
        self._confirmation_granted = False
        self._confirmed_method: str = "VOICE"
        self._confirmed_phrase: Optional[str] = None
        self._active_paypal_order_id: Optional[str] = None
        cart_service.register_change_callback(self.invalidate_on_cart_change)

    @staticmethod
    def _snapshot_cart_items(cart) -> str:
        return json.dumps(
            [
                {
                    "product_id": item.product_id,
                    "title": item.product.title,
                    "unit_price": round(float(item.product.price), 2),
                    "quantity": int(item.quantity),
                    "line_total": round(float(item.item_total), 2),
                    "variant": item.selected_variant or {},
                }
                for item in cart.items
            ],
            sort_keys=True,
        )

    def invalidate_on_cart_change(self, reason: str) -> None:
        if not self._active_review or self._state in (
            PurchaseState.PAYMENT_COMPLETE,
            PurchaseState.CANCELLED,
        ):
            return
        self._active_review.is_invalidated = True
        self._active_review.invalidation_reason = reason
        self._confirmation_granted = False
        self._is_processing = False
        self._active_paypal_order_id = None
        has_items = bool(cart_service.get_cart().items)
        self._state = PurchaseState.PAYMENT_REVIEW if has_items else PurchaseState.BROWSING
        db.log_audit_event("CART_MODIFIED_REVIEW_INVALIDATED", reason, "SYSTEM")

    def get_state(self) -> PurchaseState:
        return self._state

    def get_active_review(self) -> Optional[PurchaseReview]:
        return self._active_review

    def is_confirmation_granted(self) -> bool:
        return bool(
            self._active_review
            and not self._active_review.is_invalidated
            and self._confirmation_granted
        )

    def get_confirmed_details(self) -> Dict[str, Any]:
        return {
            "method": self._confirmed_method,
            "phrase": self._confirmed_phrase,
            "paypal_order_id": self._active_paypal_order_id,
        }

    def set_active_paypal_order_id(self, order_id: Optional[str]):
        self._active_paypal_order_id = order_id

    def get_active_paypal_order_id(self) -> Optional[str]:
        return self._active_paypal_order_id

    def set_state(self, new_state: PurchaseState, reason: str = ""):
        old_state = self._state
        self._state = new_state
        db.log_audit_event("STATE_TRANSITION", f"{old_state.value} -> {new_state.value}. Reason: {reason}", "SYSTEM")

    def prepare_payment_review(self) -> PurchaseReview:
        """
        Transitions from CART to PAYMENT_REVIEW.
        Calculates all totals, checks adaptive confirmation rules,
        free-trial/subscription terms, and creates a cryptographic review token.
        CRITICAL: Preparing review NEVER triggers payment!
        """
        cart = cart_service.get_cart()
        if not cart.items:
            raise ValueError("Cart is empty. Cannot prepare payment review.")

        prefs = accessibility_service.get_preferences()

        # Determine high value (> $500 threshold)
        is_high_value = cart.total_today >= prefs.double_confirmation_threshold
        high_value_total_steps = 2 if is_high_value else 1

        # Expected exact phrase formatting: "Confirm $59.36 purchase"
        expected_phrase = f"Confirm ${cart.total_today:.2f} purchase"

        # Check subscription guardian
        is_sub = cart.has_subscriptions
        sub_terms = cart.future_payments if is_sub else None

        # Check trial guardian
        is_trial = cart.has_trials
        trial_terms = cart.future_payments if is_trial else None

        # Warnings
        qty_warning = None
        if prefs.warn_quantity_greater_one and any(item.quantity > 1 for item in cart.items):
            multi_items = [f"{i.quantity}x {i.product.title}" for i in cart.items if i.quantity > 1]
            qty_warning = f"Notice: Multiple units selected: {', '.join(multi_items)}"

        ship_warning = None
        if cart.shipping_total > prefs.warn_shipping_exceeds:
            ship_warning = f"Notice: Shipping charge is ${cart.shipping_total:.2f}"

        review_token = f"rev_{uuid.uuid4().hex[:12]}"
        variant_snapshot = json.dumps(
            [item.selected_variant for item in cart.items],
            sort_keys=True
        )
        items_snapshot = self._snapshot_cart_items(cart)

        self._active_review = PurchaseReview(
            state=PurchaseState.PAYMENT_REVIEW,
            cart=cart,
            item_subtotal=cart.subtotal,
            shipping=cart.shipping_total,
            tax=cart.tax_total,
            discount=cart.discount_total,
            total_today=cart.total_today,
            future_payments=cart.future_payments or "None",
            is_high_value=is_high_value,
            high_value_step=1,
            high_value_total_steps=high_value_total_steps,
            requires_exact_phrase=prefs.exact_price_confirmation,
            expected_phrase=expected_phrase,
            is_subscription=is_sub,
            subscription_terms=sub_terms,
            subscription_acknowledged=False,
            is_free_trial=is_trial,
            trial_terms=trial_terms,
            trial_acknowledged=False,
            quantity_warning=qty_warning,
            shipping_warning=ship_warning,
            snapshot_total=cart.total_today,
            snapshot_shipping=cart.shipping_total,
            snapshot_item_subtotal=cart.subtotal,
            snapshot_tax=cart.tax_total,
            snapshot_quantity=cart.item_count,
            snapshot_variant=variant_snapshot,
            snapshot_items=items_snapshot,
            snapshot_recurring_terms=cart.future_payments or "None",
            review_token=review_token,
            is_invalidated=False
        )

        self._state = PurchaseState.PAYMENT_REVIEW
        self._is_processing = False
        self._confirmation_granted = False
        self._active_paypal_order_id = None

        db.log_audit_event(
            "PAYMENT_REVIEW_PREPARED",
            f"Review token: {review_token}, Total: ${cart.total_today:.2f}, HighValue: {is_high_value}",
            prefs.current_mode
        )
        return self._active_review

    def verify_price_integrity(self) -> Tuple[bool, Optional[str]]:
        """
        Price-Change & Total-Change Protection:
        Detects if ANY of the following changed from the active review snapshot:
        - Price (item_subtotal)
        - Shipping
        - Tax
        - Total
        - Quantity
        - Variant
        - Recurring terms
        If any difference is detected, immediately invalidates previous confirmation.
        """
        if not self._active_review:
            return False, "No active payment review found."

        if self._active_review.is_invalidated:
            return False, self._active_review.invalidation_reason or "Previous confirmation was invalidated due to a price or cart change."

        current_cart = cart_service.get_cart()
        if not current_cart.items:
            return False, "Your cart is empty."

        current_variant_snapshot = json.dumps(
            [item.selected_variant for item in current_cart.items],
            sort_keys=True
        )
        current_items_snapshot = self._snapshot_cart_items(current_cart)
        current_recurring = current_cart.future_payments or "None"

        reason: Optional[str] = None
        if current_cart.item_count != self._active_review.snapshot_quantity:
            reason = (
                f"The item quantity changed from {self._active_review.snapshot_quantity} "
                f"to {current_cart.item_count}.\n\nPlease review the updated total."
            )
        elif current_variant_snapshot != self._active_review.snapshot_variant:
            reason = "The selected product variant changed.\n\nPlease review the updated total."
        elif self._active_review.snapshot_items and current_items_snapshot != self._active_review.snapshot_items:
            reason = "The cart items or prices changed.\n\nPlease review the updated total."
        elif current_recurring != self._active_review.snapshot_recurring_terms:
            reason = "The recurring payment terms changed.\n\nPlease review the updated total."
        elif round(current_cart.subtotal, 2) != round(self._active_review.snapshot_item_subtotal, 2):
            reason = (
                f"The price changed from ${self._active_review.snapshot_item_subtotal:.2f} "
                f"to ${current_cart.subtotal:.2f}.\n\nPlease review the updated total."
            )
        elif round(current_cart.shipping_total, 2) != round(self._active_review.snapshot_shipping, 2):
            reason = (
                f"The shipping cost changed from ${self._active_review.snapshot_shipping:.2f} "
                f"to ${current_cart.shipping_total:.2f}.\n\nPlease review the updated total."
            )
        elif round(current_cart.tax_total, 2) != round(self._active_review.snapshot_tax, 2):
            reason = (
                f"The estimated tax changed from ${self._active_review.snapshot_tax:.2f} "
                f"to ${current_cart.tax_total:.2f}.\n\nPlease review the updated total."
            )
        elif round(current_cart.total_today, 2) != round(self._active_review.snapshot_total, 2):
            reason = (
                f"The price changed from ${self._active_review.snapshot_total:.2f} "
                f"to ${current_cart.total_today:.2f}.\n\nPlease review the updated total."
            )

        if reason:
            self._active_review.is_invalidated = True
            self._active_review.invalidation_reason = reason
            self._confirmation_granted = False
            self._is_processing = False
            self._active_paypal_order_id = None
            self._state = PurchaseState.PAYMENT_REVIEW
            db.log_audit_event("PRICE_INTEGRITY_BREACH", reason, "SYSTEM")
            return False, reason

        return True, None

    def simulate_price_change(self, new_item_price: float) -> PurchaseReview:
        """
        Demo simulation for Scenario 9: Price changes (e.g. from $54.99 to $62.99) before payment.
        Immediately invalidates previous confirmation and requires new review & confirmation.
        """
        if not self._active_review:
            self.prepare_payment_review()

        old_price = self._active_review.snapshot_item_subtotal or self._active_review.snapshot_total

        # Also update the live cart item price so recalculation reflects the new price
        cart = cart_service.get_cart()
        if cart.items:
            first_item = cart.items[0]
            first_item.product.price = new_item_price
            first_item.item_total = round(new_item_price * first_item.quantity, 2)

        # Invalidate review & revoke confirmation
        self._active_review.is_invalidated = True
        self._active_review.invalidation_reason = (
            f"The price changed from ${old_price:.2f} to ${new_item_price:.2f}.\n\n"
            "Please review the updated total."
        )
        self._confirmation_granted = False
        self._is_processing = False
        self._active_paypal_order_id = None
        self._state = PurchaseState.PAYMENT_REVIEW
        db.log_audit_event(
            "SIMULATED_PRICE_CHANGE",
            f"Price altered from ${old_price:.2f} to ${new_item_price:.2f}",
            "DEMO"
        )
        return self._active_review

    def validate_confirmation(
        self,
        token: str,
        spoken_phrase: Optional[str] = None,
        confirmation_method: str = "VOICE",
        subscription_ack: Optional[bool] = None,
        trial_ack: Optional[bool] = None,
        high_value_step: Optional[int] = None
    ) -> PurchaseResponse:
        """
        The Core Confirmation Guardian (Deterministic — NEVER delegates to LLM):
        - Prevents ambiguous commands ("yes", "looks good", "get it", "buy it")
        - Requires exact phrase if enabled
        - Enforces two-step confirmation on high value (> $500)
        - Enforces explicit recurring payment acknowledgement
        - Re-checks price, shipping, tax, quantity, variant, and recurring terms integrity
        """
        # Duplicate payment lock
        if self._is_processing:
            return PurchaseResponse(
                success=False,
                state=self._state,
                message="A payment transaction is already processing. Duplicate payment prevented.",
                is_ambiguous=False
            )

        if not self._active_review or self._active_review.review_token != token:
            return PurchaseResponse(
                success=False,
                state=self._state,
                message="Invalid or expired payment review session. Please review your cart again.",
                is_ambiguous=False
            )

        if self._active_review.is_invalidated:
            return PurchaseResponse(
                success=False,
                state=PurchaseState.PAYMENT_REVIEW,
                message=self._active_review.invalidation_reason or "The price changed. Please review the updated total.",
                is_ambiguous=False
            )

        # 1. Price & Total integrity check
        valid_price, price_error = self.verify_price_integrity()
        if not valid_price:
            return PurchaseResponse(
                success=False,
                state=PurchaseState.PAYMENT_REVIEW,
                message=price_error or "The price changed. Please review the updated total.",
                is_ambiguous=False
            )

        phrase_norm = (spoken_phrase or "").strip().lower()
        clean_phrase = re.sub(r"[^\w\s]", "", phrase_norm).strip()

        # 2. Ambiguity Protection
        # If user says something vague like "that looks good", "yes", "okay", "buy it", "go ahead", "get it"
        if phrase_norm in AMBIGUOUS_PHRASES or clean_phrase in AMBIGUOUS_PHRASES:
            db.log_audit_event("AMBIGUITY_DETECTED", f"Rejected ambiguous phrase: '{spoken_phrase}'", confirmation_method)
            return PurchaseResponse(
                success=False,
                state=PurchaseState.CONFIRMATION_REQUIRED,
                message=(
                    f"I heard '{spoken_phrase}'. No payment has been made. "
                    f"To authorize payment of ${self._active_review.total_today:.2f}, "
                    f"say: '{self._active_review.expected_phrase}' or activate the Confirm button."
                ),
                is_ambiguous=True
            )

        # 3. Subscription & Free Trial Acknowledgement Guard
        if self._active_review.is_subscription and not subscription_ack:
            db.log_audit_event("SUBSCRIPTION_UNACKNOWLEDGED", "Subscription acknowledgement missing", confirmation_method)
            return PurchaseResponse(
                success=False,
                state=PurchaseState.CONFIRMATION_REQUIRED,
                message="This is a recurring subscription. Explicit acknowledgement of recurring terms is required before payment can proceed.",
                is_ambiguous=False
            )

        if self._active_review.is_free_trial and not trial_ack:
            db.log_audit_event("TRIAL_UNACKNOWLEDGED", "Trial renewal acknowledgement missing", confirmation_method)
            return PurchaseResponse(
                success=False,
                state=PurchaseState.CONFIRMATION_REQUIRED,
                message="This purchase includes an auto-renewing trial. Explicit acknowledgement of future charges is required.",
                is_ambiguous=False
            )

        # Record acknowledgements on the active review once verified
        if subscription_ack:
            self._active_review.subscription_acknowledged = True
        if trial_ack:
            self._active_review.trial_acknowledged = True

        # 4. High-Value Two-Step Confirmation (> $500)
        if self._active_review.is_high_value:
            current_step = high_value_step or self._active_review.high_value_step
            if current_step == 1:
                # Advance to Step 2
                self._active_review.high_value_step = 2
                db.log_audit_event(
                    "HIGH_VALUE_STEP_1_PASSED",
                    f"High value purchase ${self._active_review.total_today:.2f} advanced to final confirmation",
                    confirmation_method
                )
                return PurchaseResponse(
                    success=False,
                    state=PurchaseState.CONFIRMATION_REQUIRED,
                    message=(
                        f"Step 1 verified: This purchase costs ${self._active_review.total_today:.2f}. "
                        f"For final confirmation, say: '{self._active_review.expected_phrase}'"
                    ),
                    requires_step=2,
                    is_ambiguous=False
                )

        # 5. Exact Phrase Validation (Voice Mode)
        if confirmation_method == "VOICE" and self._active_review.requires_exact_phrase:
            expected_norm = self._active_review.expected_phrase.lower()
            clean_input = re.sub(r"[^\w\s\.]", "", phrase_norm)
            clean_expected = re.sub(r"[^\w\s\.]", "", expected_norm)

            amount_str = f"{self._active_review.total_today:.2f}"

            is_valid_phrase = (
                clean_input == clean_expected
                or ("confirm" in clean_input and amount_str in clean_input)
            )

            if not is_valid_phrase:
                db.log_audit_event(
                    "EXACT_PHRASE_MISMATCH",
                    f"Spoken: '{spoken_phrase}' does not match expected: '{self._active_review.expected_phrase}'",
                    confirmation_method
                )
                return PurchaseResponse(
                    success=False,
                    state=PurchaseState.CONFIRMATION_REQUIRED,
                    message=(
                        f"Exact confirmation required. Your total is ${self._active_review.total_today:.2f}. "
                        f"Say: '{self._active_review.expected_phrase}' to continue."
                    ),
                    is_ambiguous=False
                )

        # All gates passed! Move to PAYMENT_PROCESSING (ready for PayPal Sandbox checkout)
        self._state = PurchaseState.PAYMENT_PROCESSING
        self._is_processing = True
        self._confirmation_granted = True
        self._confirmed_method = confirmation_method
        self._confirmed_phrase = spoken_phrase or f"CONFIRM ${self._active_review.total_today:.2f}"

        db.log_audit_event(
            "EXPLICIT_CONFIRMATION_GRANTED",
            f"Method: {confirmation_method}, Total: ${self._active_review.total_today:.2f}",
            confirmation_method
        )

        return PurchaseResponse(
            success=True,
            state=PurchaseState.PAYMENT_PROCESSING,
            message="Confirmation verified. Proceeding to PayPal Sandbox checkout.",
            amount_charged=self._active_review.total_today,
            is_ambiguous=False
        )

    def cancel_purchase(self, reason: str = "User invoked cancellation") -> PurchaseResponse:
        """
        Cancel Anytime:
        Voice: 'Cancel.' Large control: CANCEL. Keyboard: Escape. Switch: select CANCEL.
        Result: 'Purchase cancelled.\n\nNo payment was made.'
        """
        self._state = PurchaseState.CANCELLED
        self._is_processing = False
        self._confirmation_granted = False
        self._active_paypal_order_id = None
        db.log_audit_event("PURCHASE_CANCELLED", reason, "USER")
        return PurchaseResponse(
            success=True,
            state=PurchaseState.CANCELLED,
            message="Purchase cancelled.\n\nNo payment was made.",
            is_ambiguous=False
        )

    def complete_payment(
        self,
        order_id: str,
        paypal_order_id: str,
        paypal_capture_id: Optional[str] = None,
        product_title: Optional[str] = None,
        merchant: Optional[str] = None,
        amount_charged: Optional[float] = None,
        is_subscription: Optional[bool] = None,
        items: Optional[List[OrderLineItem]] = None,
        item_subtotal: Optional[float] = None,
        shipping: Optional[float] = None,
        tax: Optional[float] = None,
    ) -> PurchaseResponse:
        self._state = PurchaseState.PAYMENT_COMPLETE
        self._is_processing = False
        self._confirmation_granted = False
        self._active_paypal_order_id = None
        db.log_audit_event(
            "PAYMENT_COMPLETED",
            f"Order: {order_id}, PayPal Order: {paypal_order_id}, Capture: {paypal_capture_id}",
            "SYSTEM"
        )
        return PurchaseResponse(
            success=True,
            state=PurchaseState.PAYMENT_COMPLETE,
            order_id=order_id,
            paypal_order_id=paypal_order_id,
            paypal_capture_id=paypal_capture_id,
            product_title=product_title,
            merchant=merchant,
            amount_charged=amount_charged,
            item_subtotal=item_subtotal,
            shipping=shipping,
            tax=tax,
            items=items or [],
            is_subscription=is_subscription,
            message="Payment successful",
            is_ambiguous=False
        )

    def fail_payment(self, technical_reason: str) -> PurchaseResponse:
        """
        Logs the technical reason in backend audit logs ONLY,
        and returns an accessible user-facing failure message.
        Releases the in-flight lock so the user can choose [ Try Again ] or [ Cancel ].
        """
        self._state = PurchaseState.PAYMENT_FAILED
        self._is_processing = False
        self._active_paypal_order_id = None
        db.log_audit_event("PAYMENT_FAILED", technical_reason, "PAYMENT_GATEWAY")
        return PurchaseResponse(
            success=False,
            state=PurchaseState.PAYMENT_FAILED,
            message="Your payment could not be completed.\n\nNothing was charged.",
            is_ambiguous=False
        )

    def reset(self):
        self._state = PurchaseState.BROWSING
        self._active_review = None
        self._is_processing = False
        self._confirmation_granted = False
        self._confirmed_method = "VOICE"
        self._confirmed_phrase = None
        self._active_paypal_order_id = None


confirmation_service = ConfirmationService()
