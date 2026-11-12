import re
import json
import logging
import httpx
from typing import Dict, Any, List, Optional
from app.config import settings
from app.models.product import Product
from app.services.product_service import product_service
from app.services.search_engine import (
    StructuredSearchIntent,
    build_broadened_queries,
    build_typed_constraints,
    extract_search_intent_rules,
    score_and_filter_candidates,
)
from app.services.shopping_session import (
    ConversationalAction,
    ShoppingSession,
    StructuredActionOutput,
    classify_user_action,
    normalize_conversational_transcript,
    parse_ordinal_index,
    parse_quantity_number,
    resolve_product_references,
)
from app.services.cart_service import cart_service
from app.services.confirmation_service import confirmation_service
from app.services.order_service import order_service
from app.services.saved_service import saved_service
from app.models.purchase import PurchaseState

logger = logging.getLogger("accesspay.ai")
DEFAULT_DISPLAY_LIMIT = 6


def extract_search_parameters(user_text: str, last_product_type: str = "") -> Dict[str, Any]:
    """
    Backwards-compatible wrapper around the generic StructuredSearchIntent extractor.
    Preserves brand/franchise/model/color/compatibility keywords and avoids overwriting
    unrelated new queries with stale context.
    """
    prior = (
        StructuredSearchIntent(raw_query=last_product_type, search_query=last_product_type, product_type=last_product_type)
        if last_product_type
        else None
    )
    intent = extract_search_intent_rules(user_text, last_intent=prior)
    return {
        "product_type": intent.search_query,
        "core_product_type": intent.product_type,
        "max_price": intent.max_price,
        "min_price": intent.min_price,
        "requirements": intent.features,
        "color": intent.color,
        "compatibility": intent.compatibility,
        "is_followup": intent.is_followup,
    }


def _to_product_model(raw: Dict[str, Any]) -> Optional[Product]:
    try:
        return Product(**raw)
    except Exception:
        return None


class MockAIService:
    """
    Authoritative Session-Driven Agentic Commerce Engine:
    Maintains a single active ShoppingSession with monotonic search generations,
    generic reference resolution, hard/soft constraints, and zero hallucination.
    AI DOES THE NAVIGATING. YOU MAKE THE DECISIONS.
    """

    def __init__(self):
        self.session: ShoppingSession = ShoppingSession()
        self.conversation_history: List[Dict[str, str]] = []
        self.last_response: str = "Ready. Tell me what you are looking for."
        self.voice_turn_count: int = 0

    # Backwards-compatible property accessors bound cleanly to the single ShoppingSession
    @property
    def current_search_results(self) -> List[Dict[str, Any]]:
        return self.session.displayed_products

    @current_search_results.setter
    def current_search_results(self, val: List[Dict[str, Any]]):
        self.session.displayed_products = val

    @property
    def selected_product(self) -> Optional[Dict[str, Any]]:
        return self.session.selected_product

    @selected_product.setter
    def selected_product(self, val: Optional[Dict[str, Any]]):
        self.session.selected_product = val

    @property
    def last_product_type(self) -> str:
        return self.session.structured_search_intent.search_query if self.session.structured_search_intent else self.session.product_type

    @last_product_type.setter
    def last_product_type(self, val: str):
        self.session.product_type = val

    @property
    def last_max_price(self) -> Optional[float]:
        return self.session.price_constraints.get("max_price")

    @last_max_price.setter
    def last_max_price(self, val: Optional[float]):
        self.session.price_constraints["max_price"] = val

    @property
    def last_requirements(self) -> List[str]:
        return self.session.features

    @last_requirements.setter
    def last_requirements(self, val: List[str]):
        self.session.features = list(val)

    @property
    def last_search_intent(self) -> Optional[StructuredSearchIntent]:
        return self.session.structured_search_intent

    @last_search_intent.setter
    def last_search_intent(self, val: Optional[StructuredSearchIntent]):
        self.session.structured_search_intent = val

    @property
    def candidate_offset(self) -> int:
        return self.session.candidate_offset

    @candidate_offset.setter
    def candidate_offset(self, val: int):
        self.session.candidate_offset = val

    def reset_conversation(self):
        self.conversation_history = []
        self.session.reset()
        self.last_response = "Ready. Tell me what you are looking for."
        product_service.reset_session()

    def _current_shown_brands(self) -> List[str]:
        return self.session.shown_brands()

    def _sync_cart_snapshot(self):
        self.session.cart = cart_service.get_cart().model_dump()

    def _prepare_turn_context(
        self,
        user_text: str,
        input_mode: str = "text",
        active_search_id: Optional[str] = None,
        search_generation: Optional[int] = None,
        visible_product_ids: Optional[List[str]] = None,
        raw_transcript: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_mode = (input_mode or "text").strip().lower() or "text"
        raw_text = raw_transcript if raw_transcript is not None else user_text
        normalized_text = normalize_conversational_transcript(user_text)
        ctx = dict(context_data or {})
        current_view = str(ctx.get("current_view") or "SHOP").upper()
        # Recover displayed_products from product_service lookup ONLY if active session has none
        # and active_search_id matches current session (never resurrect stale prior-generation cards).
        if (
            not self.session.displayed_products
            and visible_product_ids
            and (not active_search_id or active_search_id == self.session.search_id or self.session.search_generation == 0)
        ):
            recovered = []
            for pid in visible_product_ids:
                prod_obj = product_service.get_product_by_id(pid)
                if prod_obj:
                    recovered.append(prod_obj.model_dump())
            if recovered:
                self.session.displayed_products = recovered
                if not self.session.candidate_products:
                    self.session.candidate_products = list(recovered)

        synced_visible_ids = self.session.synchronize_visible_products(
            active_search_id=active_search_id,
            search_generation=search_generation,
            visible_product_ids=visible_product_ids,
        )
        voice_turn = None
        if normalized_mode == "voice":
            self.voice_turn_count += 1
            voice_turn = self.voice_turn_count
        return {
            "input_mode": normalized_mode,
            "voice_turn": voice_turn,
            "raw_transcript": raw_text if normalized_mode == "voice" else None,
            "normalized_text": normalized_text,
            "current_view": current_view,
            "context_data": ctx,
            "active_search_id": self.session.search_id,
            "search_generation": self.session.search_generation,
            "visible_product_ids": visible_product_ids if visible_product_ids is not None else synced_visible_ids,
        }

    @staticmethod
    def _pick_entity_by_context(
        items: List[Any],
        id_attr: str,
        text: str,
        visible_ids: Optional[List[str]] = None,
        selected_id: Optional[str] = None,
    ) -> Optional[Any]:
        if not items:
            return None
        by_id = {(getattr(x, id_attr) if hasattr(x, id_attr) else x.get(id_attr)): x for x in items}
        ordered = items
        if visible_ids:
            reordered = [by_id[eid] for eid in visible_ids if eid in by_id]
            for x in items:
                k = getattr(x, id_attr) if hasattr(x, id_attr) else x.get(id_attr)
                if k not in visible_ids:
                    reordered.append(x)
            if reordered:
                ordered = reordered
        idx = parse_ordinal_index(text)
        if idx is not None:
            if idx == -1:
                return ordered[0] if any(w in text.lower() for w in ("last", "latest", "recent", "previous")) else ordered[-1]
            if 0 <= idx < len(ordered):
                return ordered[idx]
        if selected_id and selected_id in by_id:
            return by_id[selected_id]
        return None

    def _empty_transcript_response(self, turn_ctx: Dict[str, Any]) -> Dict[str, Any]:
        msg = "I didn't catch that. Please repeat your command."
        self.last_response = msg
        action_out = StructuredActionOutput(
            action=ConversationalAction.CLARIFICATION_NEEDED,
            needs_clarification=True,
            clarification_question=msg,
        )
        payload: Dict[str, Any] = {
            "action": "CLARIFICATION_NEEDED",
            "needs_clarification": True,
            "message": msg,
            "speech_response": msg,
            "provider": "unified",
        }
        self._attach_session_metadata(
            payload,
            action_out,
            channel3_called=False,
            referenced_ids=[],
            input_mode=turn_ctx["input_mode"],
        )
        self._log_turn(
            turn_ctx["normalized_text"],
            self.session.last_action,
            self.session.search_generation,
            action_out,
            channel3_called=False,
            referenced_ids=[],
            turn_ctx=turn_ctx,
            resolved_action=payload["action"],
        )
        return payload

    def _log_turn(
        self,
        user_text: str,
        prev_action: str,
        prev_gen: int,
        action_out: StructuredActionOutput,
        channel3_called: bool,
        referenced_ids: Optional[List[str]] = None,
        turn_ctx: Optional[Dict[str, Any]] = None,
        resolved_action: Optional[str] = None,
    ):
        backend_displayed_ids = [p.get("id") for p in self.session.displayed_products if p.get("id")]
        visible_ids = (turn_ctx or {}).get("visible_product_ids") or backend_displayed_ids
        resolved_ids = referenced_ids or []
        raw_voice = (turn_ctx or {}).get("raw_transcript")
        input_mode = (turn_ctx or {}).get("input_mode", "text")
        voice_turn = (turn_ctx or {}).get("voice_turn")
        current_view = (turn_ctx or {}).get("current_view", "SHOP")
        detected_act = resolved_action or action_out.action.value
        if logger.isEnabledFor(logging.INFO):
            logger.info(
                "[VoiceTrace] VOICE_TURN=%s RAW_VOICE_TRANSCRIPT=%r NORMALIZED_TRANSCRIPT=%r INPUT_MODE=%s "
                "CURRENT_VIEW=%s ACTIVE_SEARCH_ID=%s SEARCH_GENERATION=%d VISIBLE_PRODUCT_IDS=%s BACKEND_DISPLAYED_IDS=%s "
                "DETECTED_ACTION=%s CHANNEL3_CALLED=%s RESOLVED_PRODUCT_IDS=%s",
                voice_turn,
                raw_voice,
                user_text,
                input_mode,
                current_view,
                self.session.search_id,
                self.session.search_generation,
                visible_ids,
                backend_displayed_ids,
                detected_act,
                channel3_called,
                resolved_ids,
            )
            logger.info(
                "[SessionDebug] msg=%r action=%s gen=%d transition='%s@%d->%s@%d' c3_called=%s refs=%s selected=%s candidates=%s intent=%s",
                user_text,
                action_out.action.value,
                self.session.search_generation,
                prev_action,
                prev_gen,
                self.session.last_action,
                self.session.search_generation,
                channel3_called,
                resolved_ids,
                (self.session.selected_product or {}).get("id"),
                [p.get("id") for p in self.session.displayed_products],
                self.session.structured_search_intent.search_query if self.session.structured_search_intent else None,
            )

    def _attach_session_metadata(
        self,
        payload: Dict[str, Any],
        action_out: StructuredActionOutput,
        channel3_called: bool = False,
        referenced_ids: Optional[List[str]] = None,
        input_mode: str = "text",
    ) -> Dict[str, Any]:
        resolved_ids = referenced_ids or []
        payload["input_mode"] = input_mode
        payload["classified_action"] = action_out.action.value
        payload["search_generation"] = self.session.search_generation
        payload["search_id"] = self.session.search_id
        payload["session_id"] = self.session.session_id
        payload["channel3_called"] = channel3_called
        payload["referenced_product_ids"] = resolved_ids
        payload["resolved_product_ids"] = resolved_ids
        payload["displayed_product_ids"] = [p.get("id") for p in self.session.displayed_products]
        payload["has_more"] = self.session.has_more
        payload["total_available"] = self.session.total_available
        payload["structured_action"] = action_out.model_dump()
        return payload

    async def process_user_intent(
        self,
        user_text: str,
        input_mode: str = "text",
        active_search_id: Optional[str] = None,
        search_generation: Optional[int] = None,
        visible_product_ids: Optional[List[str]] = None,
        raw_transcript: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        turn_ctx = self._prepare_turn_context(
            user_text,
            input_mode=input_mode,
            active_search_id=active_search_id,
            search_generation=search_generation,
            visible_product_ids=visible_product_ids,
            raw_transcript=raw_transcript,
            context_data=context_data,
        )
        text = turn_ctx["normalized_text"]
        if not text:
            return self._empty_transcript_response(turn_ctx)
        self.conversation_history.append({"role": "user", "text": text})
        action_out = classify_user_action(text, self.session, context=turn_ctx.get("context_data"))
        return await self.execute_classified_action(text, action_out, turn_ctx=turn_ctx)

    async def execute_classified_action(
        self,
        user_text: str,
        action_out: StructuredActionOutput,
        provider_label: str = "mock",
        turn_ctx: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        text = user_text.strip()
        text_lower = text.lower()
        prev_action = self.session.last_action
        prev_gen = self.session.search_generation
        self.session.last_user_message = text
        input_mode = (turn_ctx or {}).get("input_mode", "text")
        ctx_data = (turn_ctx or {}).get("context_data") or {}
        current_view = str((turn_ctx or {}).get("current_view") or "SHOP").upper()

        def finalize(res: Dict[str, Any], channel3_called: bool = False, refs: Optional[List[str]] = None) -> Dict[str, Any]:
            res.setdefault("provider", provider_label)
            self.session.last_action = res.get("action", action_out.action.value)
            if self.session.last_action != "CLARIFICATION_NEEDED":
                self.session.pending_clarification = None
            self._sync_cart_snapshot()
            self._attach_session_metadata(
                res,
                action_out,
                channel3_called=channel3_called,
                referenced_ids=refs,
                input_mode=input_mode,
            )
            self._log_turn(
                text,
                prev_action,
                prev_gen,
                action_out,
                channel3_called=channel3_called,
                referenced_ids=refs,
                turn_ctx=turn_ctx,
                resolved_action=res.get("action"),
            )
            return res

        # 1. Confirmation Attempt & Accidental Checkout Guard
        if action_out.action == ConversationalAction.CONFIRMATION_ATTEMPT:
            is_explicit_confirm = "confirm" in text_lower and ("$" in text_lower or any(ch.isdigit() for ch in text_lower))
            if is_explicit_confirm:
                review = confirmation_service.get_active_review()
                if not review and cart_service.get_cart().items:
                    review = confirmation_service.prepare_payment_review()
                if review:
                    resp = confirmation_service.validate_confirmation(
                        token=review.review_token,
                        spoken_phrase=text,
                        confirmation_method="VOICE",
                        subscription_ack=review.subscription_acknowledged,
                        trial_ack=review.trial_acknowledged,
                        high_value_step=review.high_value_step,
                    )
                    self.last_response = resp.message
                    return finalize({
                        "action": "PAYMENT_CONFIRMED" if resp.success else "CONFIRMATION_FAILED",
                        "message": resp.message,
                        "speech_response": resp.message,
                        "state": resp.state,
                        "success": resp.success,
                        "amount_charged": resp.amount_charged,
                        "requires_step": resp.requires_step,
                        "review_token": review.review_token,
                    })

            state = confirmation_service.get_state()
            if state in [PurchaseState.PAYMENT_REVIEW, PurchaseState.CONFIRMATION_REQUIRED]:
                review = confirmation_service.get_active_review()
                if review:
                    resp = confirmation_service.validate_confirmation(
                        token=review.review_token,
                        spoken_phrase=text,
                        confirmation_method="VOICE",
                    )
                    self.last_response = resp.message
                    return finalize({
                        "action": "AMBIGUITY_GUARD",
                        "message": resp.message,
                        "speech_response": resp.message,
                        "is_ambiguous": True,
                        "state": resp.state,
                    })

            msg = "I heard you, but that command does not authorize payment. AI does the navigating; you authorize the final payment."
            self.last_response = msg
            return finalize({
                "action": "AMBIGUITY_GUARD",
                "message": msg,
                "speech_response": msg,
                "is_ambiguous": True,
            })

        # 2. Cancel & Checkout / Payment-Stage Helpers
        if action_out.action == ConversationalAction.OPEN_SHOP:
            msg = "Opening Shop."
            self.last_response = msg
            return finalize({"action": "OPEN_SHOP", "message": msg, "speech_response": msg}, channel3_called=False)

        if action_out.action == ConversationalAction.READ_REVIEW:
            review = confirmation_service.get_active_review()
            if not review and cart_service.get_cart().items:
                review = confirmation_service.prepare_payment_review()
            if not review:
                msg = "Your cart is empty. Select a product before reviewing an order."
                self.last_response = msg
                return finalize({"action": "INFO", "message": msg, "speech_response": msg})
            items_summary = "; ".join(
                f"{it.product.title} (${it.product.price:.2f} × {it.quantity})" for it in review.cart.items
            )
            sub_note = " Includes a recurring monthly charge." if review.is_subscription else ""
            msg = (
                f"Purchase Review: {items_summary}. "
                f"Subtotal ${review.item_subtotal:.2f}, shipping ${review.shipping:.2f}, tax ${review.tax:.2f}. "
                f"Total today is ${review.total_today:.2f}.{sub_note} No payment has been made yet."
            )
            self.last_response = msg
            return finalize({
                "action": "READ_REVIEW",
                "review": review.model_dump(),
                "message": msg,
                "speech_response": msg,
            }, channel3_called=False)

        if action_out.action == ConversationalAction.PROCEED_TO_CONFIRMATION:
            review = confirmation_service.get_active_review()
            if not review and cart_service.get_cart().items:
                review = confirmation_service.prepare_payment_review()
            if not review:
                msg = "Your cart is empty."
                self.last_response = msg
                return finalize({"action": "INFO", "message": msg, "speech_response": msg})
            msg = f"Your total is ${review.total_today:.2f}. No payment has been made yet. Say '{review.expected_phrase}' to continue."
            self.last_response = msg
            return finalize({
                "action": "PROCEED_TO_CONFIRMATION",
                "review": review.model_dump(),
                "message": msg,
                "speech_response": msg,
            }, channel3_called=False)

        if action_out.action == ConversationalAction.PAYPAL_APPROVAL_NAVIGATION:
            msg = "Opening PayPal Sandbox checkout approval."
            self.last_response = msg
            return finalize({"action": "PAYPAL_APPROVAL_NAVIGATION", "message": msg, "speech_response": msg}, channel3_called=False)

        if action_out.action == ConversationalAction.READ_RECEIPT:
            msg = "Reading your receipt."
            self.last_response = msg
            return finalize({"action": "READ_RECEIPT", "message": msg, "speech_response": msg}, channel3_called=False)

        if action_out.action == ConversationalAction.READ_ORDER_ID:
            latest_orders = order_service.get_all_orders()
            if latest_orders:
                o = latest_orders[0]
                pp = f" PayPal Order ID {o.paypal_order_id}." if o.paypal_order_id else ""
                msg = f"Your order ID is {o.order_id}.{pp}"
            else:
                msg = "No completed order ID is available yet."
            self.last_response = msg
            return finalize({"action": "READ_ORDER_ID", "message": msg, "speech_response": msg}, channel3_called=False)

        if action_out.action == ConversationalAction.RETRY_PAYMENT:
            msg = "Returning to payment confirmation so you can try again."
            self.last_response = msg
            return finalize({"action": "RETRY_PAYMENT", "message": msg, "speech_response": msg}, channel3_called=False)

        if action_out.action == ConversationalAction.CANCEL:
            confirmation_service.cancel_purchase("User commanded cancellation via AI")
            cart_service.clear()
            self.session.selected_product = None
            msg = "Purchase cancelled.\nNo payment was made."
            self.last_response = msg
            return finalize({
                "action": "CANCELLED",
                "message": msg,
                "speech_response": "Purchase cancelled. No payment was made.",
                "state": PurchaseState.CANCELLED,
            })

        # 3. Go Back
        if action_out.action == ConversationalAction.GO_BACK:
            msg = "Returning to the previous step."
            self.last_response = msg
            return finalize({
                "action": "NAVIGATE_BACK",
                "message": msg,
                "speech_response": msg,
            })

        # 3b. Saved Items, Saved Searches, and Order History (NEVER trigger product searches arbitrarily)
        if action_out.action == ConversationalAction.OPEN_PREVIOUS_ORDER:
            all_orders = order_service.get_all_orders()
            if not all_orders:
                msg = "You don't have any completed orders yet."
                self.last_response = msg
                return finalize({
                    "action": "OPEN_ORDER",
                    "order": None,
                    "orders": [],
                    "message": msg,
                    "speech_response": msg,
                }, channel3_called=False)
            latest = all_orders[0]
            msg = (
                f"Opening your previous completed order {latest.order_id} from {latest.date}: "
                f"{latest.product_title} (${latest.total:.2f})."
            )
            self.last_response = msg
            return finalize({
                "action": "OPEN_ORDER",
                "order": latest.model_dump(),
                "order_id": latest.order_id,
                "orders": [o.model_dump() for o in all_orders],
                "message": msg,
                "speech_response": msg,
            }, channel3_called=False)

        if action_out.action == ConversationalAction.OPEN_ORDER:
            all_orders = order_service.get_all_orders()
            if not all_orders:
                msg = "You don't have any completed orders yet."
                self.last_response = msg
                return finalize({
                    "action": "OPEN_ORDER",
                    "order": None,
                    "orders": [],
                    "message": msg,
                    "speech_response": msg,
                }, channel3_called=False)
            target_order = self._pick_entity_by_context(
                all_orders,
                "order_id",
                text,
                visible_ids=ctx_data.get("visible_order_ids"),
                selected_id=ctx_data.get("selected_order_id"),
            ) or all_orders[0]
            msg = (
                f"Opening order {target_order.order_id} ({target_order.date}): "
                f"{target_order.product_title} from {target_order.merchant} for ${target_order.total:.2f}."
            )
            self.last_response = msg
            return finalize({
                "action": "OPEN_ORDER",
                "order": target_order.model_dump(),
                "order_id": target_order.order_id,
                "orders": [o.model_dump() for o in all_orders],
                "message": msg,
                "speech_response": msg,
            }, channel3_called=False)

        if action_out.action == ConversationalAction.ORDER_DETAIL_QUERY:
            all_orders = order_service.get_all_orders()
            if not all_orders:
                msg = "You don't have any completed orders yet."
                self.last_response = msg
                return finalize({"action": "INFO", "message": msg, "speech_response": msg}, channel3_called=False)
            target_order = self._pick_entity_by_context(
                all_orders,
                "order_id",
                text,
                visible_ids=ctx_data.get("visible_order_ids"),
                selected_id=ctx_data.get("selected_order_id"),
            ) or all_orders[0]
            line_items = target_order.items or []
            if "shipping" in text_lower:
                msg = f"Shipping for order {target_order.order_id} was ${target_order.shipping:.2f}."
            elif "tax" in text_lower:
                msg = f"Tax for order {target_order.order_id} was ${target_order.tax:.2f}."
            elif any(w in text_lower for w in ("what did i buy", "items", "show the items")):
                if line_items:
                    desc = ", ".join(f"{li.product_title} (x{li.quantity}, ${li.line_total:.2f})" for li in line_items)
                else:
                    desc = f"{target_order.product_title} (x{target_order.quantity})"
                msg = f"In order {target_order.order_id}, you bought: {desc}. Total paid: ${target_order.total:.2f}."
            else:
                if line_items:
                    desc = ", ".join(f"{li.product_title} (x{li.quantity})" for li in line_items)
                else:
                    desc = target_order.product_title
                sub = target_order.item_subtotal if target_order.item_subtotal is not None else target_order.item_price
                msg = (
                    f"Order {target_order.order_id} ({target_order.date}): {desc}. "
                    f"Subtotal ${sub:.2f}, shipping ${target_order.shipping:.2f}, tax ${target_order.tax:.2f}, "
                    f"total ${target_order.total:.2f}."
                )
            self.last_response = msg
            return finalize({
                "action": "ORDER_DETAILS",
                "order": target_order.model_dump(),
                "order_id": target_order.order_id,
                "orders": [o.model_dump() for o in all_orders],
                "message": msg,
                "speech_response": msg,
            }, channel3_called=False)

        if action_out.action == ConversationalAction.VIEW_ORDERS:
            orders_res = order_service.query_orders_conversational(text)
            self.last_response = orders_res["message"]
            return finalize({
                "action": "OPEN_ORDERS",
                "orders": orders_res["orders"],
                "selected_order": orders_res["selected_order"],
                "message": orders_res["message"],
                "speech_response": "Opening your orders. " + orders_res["message"],
            }, channel3_called=False)

        if action_out.action == ConversationalAction.REORDER:
            try:
                all_orders = order_service.get_all_orders()
                picked_order = (
                    self._pick_entity_by_context(
                        all_orders,
                        "order_id",
                        text,
                        visible_ids=ctx_data.get("visible_order_ids"),
                        selected_id=ctx_data.get("selected_order_id"),
                    )
                    if all_orders
                    else None
                )
                target_oid = picked_order.order_id if picked_order else None
                reorder_res = await order_service.reorder_order(target_oid)
                review = reorder_res["review"]
                changes = reorder_res.get("price_changes") or []
                change_note = ""
                if changes:
                    change_note = "\nPrice notice: " + "; ".join(
                        f"{c['title']} changed from ${c['old_price']:.2f} to ${c['current_price']:.2f}"
                        for c in changes
                    )
                msg = (
                    f"Loaded items from order {reorder_res['source_order_id']} into a fresh cart.{change_note}\n"
                    f"Current total today is ${review['total_today']:.2f}.\n"
                    f"No payment has been made yet. Say '{review['expected_phrase']}' to continue."
                )
                self.last_response = msg
                return finalize({
                    "action": "PAYMENT_REVIEW_READY",
                    "review": review,
                    "price_changes": changes,
                    "source_order_id": reorder_res["source_order_id"],
                    "message": msg,
                    "speech_response": msg,
                }, channel3_called=False)
            except ValueError as exc:
                msg = str(exc)
                self.last_response = msg
                return finalize({"action": "INFO", "message": msg, "speech_response": msg})

        if action_out.action == ConversationalAction.VIEW_SAVED_ITEMS:
            items = [i.model_dump() for i in saved_service.list_saved_items()]
            if not items:
                msg = "You have no saved items yet."
            else:
                lines = [f"- {i['product_title']} (${i['price_at_save']:.2f} from {i['merchant']})" for i in items[:6]]
                msg = f"You have {len(items)} saved item{'s' if len(items) != 1 else ''}:\n" + "\n".join(lines)
            self.last_response = msg
            return finalize({
                "action": "OPEN_SAVED_ITEMS",
                "saved_items": items,
                "message": msg,
                "speech_response": msg,
            }, channel3_called=False)

        if action_out.action == ConversationalAction.SAVE_ITEM:
            multi_save = bool(re.search(r"\b(?:first\s+two|top\s+two|both|these\s+two)\b", text_lower))
            if multi_save:
                ref = resolve_product_references(text, self.session, expected_count=2, explicit_refs=action_out.references)
            else:
                ref = resolve_product_references(text, self.session, expected_count=1, explicit_refs=action_out.references)
                if ref["ambiguous"] and (self.session.selected_product or self.session.last_discussed_product) and re.search(r"\b(?:this|that|it)\b", text_lower):
                    chosen_ctx = self.session.selected_product or self.session.last_discussed_product
                    ref = {"empty_pool": False, "ambiguous": False, "products": [chosen_ctx]}
            if ref["empty_pool"]:
                return finalize({"action": "INFO", "message": ref["question"], "speech_response": ref["question"]})
            if ref["ambiguous"]:
                self.session.pending_clarification = {"action": ConversationalAction.SAVE_ITEM.value}
                self.last_response = ref["question"]
                return finalize({
                    "action": "CLARIFICATION_NEEDED",
                    "needs_clarification": True,
                    "message": ref["question"],
                    "speech_response": ref["question"],
                })
            saved_list = [saved_service.save_item(p).model_dump() for p in ref["products"]]
            titles = ", ".join(s["product_title"] for s in saved_list)
            msg = f"Saved for later: {titles}. Not added to cart; no payment was made."
            self.last_response = msg
            return finalize({
                "action": "PRODUCT_SAVED",
                "saved_item": saved_list[0],
                "saved_items": saved_list,
                "message": msg,
                "speech_response": "Product saved.",
            }, channel3_called=False, refs=[s["product_id"] for s in saved_list])

        if action_out.action == ConversationalAction.OPEN_SAVED_ITEM:
            saved_all = saved_service.list_saved_items()
            if not saved_all:
                msg = "You have no saved items yet."
                self.last_response = msg
                return finalize({"action": "INFO", "message": msg, "speech_response": msg}, channel3_called=False)
            target_saved = self._pick_entity_by_context(
                saved_all,
                "saved_item_id",
                text,
                visible_ids=ctx_data.get("visible_saved_item_ids"),
                selected_id=ctx_data.get("selected_saved_item_id"),
            ) or saved_all[0]
            attrs_note = (
                " Features: " + ", ".join(target_saved.important_attributes[:3]) + "."
                if target_saved.important_attributes
                else ""
            )
            msg = (
                f"Saved item: {target_saved.product_title} (${target_saved.price_at_save:.2f} from {target_saved.merchant})."
                f"{attrs_note}"
            )
            self.last_response = msg
            return finalize({
                "action": "OPEN_SAVED_ITEM",
                "saved_item": target_saved.model_dump(),
                "saved_item_id": target_saved.saved_item_id,
                "message": msg,
                "speech_response": msg,
            }, channel3_called=False)

        if action_out.action == ConversationalAction.ADD_SAVED_ITEM_TO_CART:
            saved_all = saved_service.list_saved_items()
            if not saved_all:
                msg = "You have no saved items to add to cart."
                self.last_response = msg
                return finalize({"action": "INFO", "message": msg, "speech_response": msg}, channel3_called=False)
            target_saved = self._pick_entity_by_context(
                saved_all,
                "saved_item_id",
                text,
                visible_ids=ctx_data.get("visible_saved_item_ids"),
                selected_id=ctx_data.get("selected_saved_item_id"),
            )
            if not target_saved:
                for s in saved_all:
                    if s.product_title.lower() in text_lower or s.product_id.lower() in text_lower:
                        target_saved = s
                        break
            if not target_saved:
                target_saved = saved_all[0]
            add_res = await saved_service.add_saved_item_to_cart(target_saved.saved_item_id)
            self.last_response = add_res["message"]
            return finalize({
                "action": "SAVED_ITEM_ADDED_TO_CART",
                "saved_item_id": target_saved.saved_item_id,
                "product": add_res["product"],
                "cart": add_res["cart"],
                "price_changed": add_res["price_changed"],
                "message": add_res["message"],
                "speech_response": add_res["message"],
            }, channel3_called=False, refs=[add_res["product"]["id"]])

        if action_out.action == ConversationalAction.REMOVE_SAVED_ITEM:
            saved_all = saved_service.list_saved_items()
            if not saved_all:
                msg = "You have no saved items to remove."
                self.last_response = msg
                return finalize({"action": "INFO", "message": msg, "speech_response": msg})
            target_saved = self._pick_entity_by_context(
                saved_all,
                "saved_item_id",
                text,
                visible_ids=ctx_data.get("visible_saved_item_ids"),
                selected_id=ctx_data.get("selected_saved_item_id"),
            )
            if not target_saved:
                for s in saved_all:
                    if s.product_title.lower() in text_lower or s.product_id.lower() in text_lower:
                        target_saved = s
                        break
            if not target_saved and (self.session.selected_product or self.session.last_discussed_product):
                ctx_id = (self.session.selected_product or self.session.last_discussed_product or {}).get("id")
                target_saved = next((s for s in saved_all if s.product_id == ctx_id), None)
            if not target_saved:
                target_saved = saved_all[0]
            saved_service.remove_saved_item(target_saved.saved_item_id)
            msg = f"Removed '{target_saved.product_title}' from saved items."
            self.last_response = msg
            return finalize({
                "action": "SAVED_ITEM_REMOVED",
                "removed_id": target_saved.saved_item_id,
                "saved_items": [s.model_dump() for s in saved_service.list_saved_items()],
                "message": msg,
                "speech_response": "Product removed from saved items.",
            }, channel3_called=False)

        if action_out.action == ConversationalAction.SAVE_SEARCH:
            if not self.session.original_query and not self.session.structured_search_intent:
                msg = "Run a product search first before saving it."
                self.last_response = msg
                return finalize({"action": "INFO", "message": msg, "speech_response": msg})
            saved_search = saved_service.save_search(
                original_query=self.session.original_query or self.session.original_user_query,
                display_query=self.session.display_query or self.session.original_query,
                structured_intent=self.session.structured_search_intent.model_dump() if self.session.structured_search_intent else {},
                filters=self.session.filters,
                sort=self.session.sort,
                reference_product_ids=[p.get("id") for p in self.session.displayed_products if p.get("id")],
            )
            msg = f"Saved search '{saved_search.display_query}' for later."
            self.last_response = msg
            return finalize({
                "action": "SEARCH_SAVED",
                "saved_search": saved_search.model_dump(),
                "message": msg,
                "speech_response": "Saved search created.",
            }, channel3_called=False)

        if action_out.action == ConversationalAction.VIEW_SAVED_SEARCHES:
            searches = [s.model_dump() for s in saved_service.list_saved_searches()]
            if not searches:
                msg = "You have no saved searches yet."
            else:
                lines = [f"- {s['display_query']}" for s in searches[:6]]
                msg = f"Your saved searches ({len(searches)}):\n" + "\n".join(lines)
            self.last_response = msg
            return finalize({
                "action": "OPEN_SAVED_SEARCHES",
                "saved_searches": searches,
                "message": msg,
                "speech_response": msg,
            }, channel3_called=False)

        if action_out.action == ConversationalAction.OPEN_SAVED_SEARCH:
            all_searches = saved_service.list_saved_searches()
            picked_search = self._pick_entity_by_context(
                all_searches,
                "saved_search_id",
                text,
                visible_ids=ctx_data.get("visible_saved_search_ids"),
            )
            if picked_search:
                return await self.run_saved_search_by_id(picked_search.saved_search_id)
            matches = saved_service.find_matching_saved_searches(text)
            if not matches:
                msg = "I couldn't find a matching saved search. Try viewing Saved Searches."
                self.last_response = msg
                return finalize({"action": "INFO", "message": msg, "speech_response": msg})
            if len(matches) > 1:
                names = ", ".join(f"'{m.display_query}'" for m in matches[:4])
                msg = f"Multiple saved searches match that request: {names}. Which saved search would you like to open?"
                self.session.pending_clarification = {"action": ConversationalAction.OPEN_SAVED_SEARCH.value}
                self.last_response = msg
                return finalize({
                    "action": "CLARIFICATION_NEEDED",
                    "needs_clarification": True,
                    "saved_searches": [m.model_dump() for m in matches],
                    "message": msg,
                    "speech_response": msg,
                })
            res = await self.run_saved_search_by_id(matches[0].saved_search_id)
            return res

        # 4. Help / Repeat
        if action_out.action == ConversationalAction.HELP:
            if any(w in text_lower for w in ("repeat", "say again", "what did you say")):
                return finalize({
                    "action": "INFO",
                    "message": self.last_response,
                    "speech_response": self.last_response,
                })
            help_msg = (
                "Tell me what product you want to find, or ask to compare, view details, "
                "show a cheaper matching option, filter results, or choose an option number."
            )
            self.last_response = help_msg
            return finalize({
                "action": "INFO",
                "message": help_msg,
                "speech_response": help_msg,
            })

        # 5. Cart & Checkout Actions (never call Channel3)
        if action_out.action in {ConversationalAction.VIEW_CART, ConversationalAction.OPEN_CART}:
            cart = cart_service.get_cart()
            is_open_nav = action_out.action == ConversationalAction.OPEN_CART
            if not cart.items:
                msg = "Your cart is currently empty. Select a product option to add it to your cart."
            else:
                lines = [
                    f"- {it.product.title} — ${it.product.price:.2f} × {it.quantity} = ${it.item_total:.2f}"
                    for it in cart.items
                ]
                distinct_count = len(cart.items)
                msg = (
                    f"Your cart has {distinct_count} product{'s' if distinct_count != 1 else ''} "
                    f"({cart.item_count} item{'s' if cart.item_count != 1 else ''}):\n"
                    + "\n".join(lines)
                    + f"\nSubtotal: ${cart.subtotal:.2f}\nShipping: ${cart.shipping_total:.2f}\nTax: ${cart.tax_total:.2f}\nTotal: ${cart.total_today:.2f}"
                )
            self.last_response = msg
            return finalize({
                "action": "OPEN_CART" if is_open_nav else "VIEW_CART",
                "cart": cart.model_dump(),
                "message": msg,
                "speech_response": msg,
            })

        if action_out.action == ConversationalAction.ADD_TO_CART:
            ref = resolve_product_references(text, self.session, expected_count=1, explicit_refs=action_out.references)
            if ref["empty_pool"]:
                return finalize({"action": "INFO", "message": ref["question"], "speech_response": ref["question"]})
            if ref["ambiguous"]:
                self.session.pending_clarification = {"action": ConversationalAction.ADD_TO_CART.value}
                self.last_response = ref["question"]
                return finalize({"action": "CLARIFICATION_NEEDED", "needs_clarification": True, "message": ref["question"], "speech_response": ref["question"]})
            chosen = ref["products"][0]
            self.session.selected_product = chosen
            updated_cart = cart_service.add_item(chosen["id"], quantity=1)
            msg = (
                f"Added {chosen['title']} to cart.\n"
                f"Price: ${chosen['price']:.2f}\n"
                f"Cart items: {updated_cart.item_count} — Cart Total: ${updated_cart.total_today:.2f}\n\n"
                f"No payment has been made yet."
            )
            self.last_response = msg
            return finalize({
                "action": "PRODUCT_SELECTED",
                "product": chosen,
                "cart": updated_cart.model_dump(),
                "message": msg,
                "speech_response": f"Added {chosen['title']} to your cart. Your cart total is ${updated_cart.total_today:.2f}. No payment has been made yet.",
            }, refs=[chosen["id"]])

        if action_out.action == ConversationalAction.CLEAR_CART:
            cart_service.clear()
            confirmation_service.reset()
            self.session.selected_product = None
            updated_cart = cart_service.get_cart()
            msg = "Cleared your cart. No payment was made."
            self.last_response = msg
            return finalize({
                "action": "CART_UPDATED",
                "cart": updated_cart.model_dump(),
                "message": msg,
                "speech_response": msg,
            }, channel3_called=False)

        if action_out.action == ConversationalAction.REMOVE_FROM_CART:
            cart = cart_service.get_cart()
            removed_specific = False
            wants_clear_all = any(w in text_lower for w in ("all", "everything", "empty", "clear"))
            if cart.items and not wants_clear_all:
                picked = self._pick_entity_by_context(
                    cart.items,
                    "product_id",
                    text,
                    visible_ids=ctx_data.get("visible_cart_product_ids"),
                )
                if picked:
                    cart_service.remove_item(picked.product_id)
                    removed_specific = True
                else:
                    for it in cart.items:
                        if it.product.title.lower() in text_lower or it.product_id.lower() in text_lower:
                            cart_service.remove_item(it.product_id)
                            removed_specific = True
                            break
            if not removed_specific and (wants_clear_all or len(cart.items) <= 1):
                cart_service.clear()
                self.session.selected_product = None
            updated_cart = cart_service.get_cart()
            msg = (
                f"Updated your cart ({updated_cart.item_count} item{'s' if updated_cart.item_count != 1 else ''}, total ${updated_cart.total_today:.2f}). No payment was made."
                if removed_specific and updated_cart.items
                else (
                    "Could not tell which cart item to remove. Try 'remove the first item' or 'clear cart'."
                    if not removed_specific and updated_cart.items
                    else "Removed items from your cart. No payment was made."
                )
            )
            self.last_response = msg
            return finalize({
                "action": "CART_UPDATED" if (removed_specific or not updated_cart.items) else "INFO",
                "cart": updated_cart.model_dump(),
                "message": msg,
                "speech_response": msg,
            })

        if action_out.action == ConversationalAction.CHANGE_QUANTITY:
            qty = max(1, int(action_out.constraint_updates.get("quantity") or parse_quantity_number(text) or 1))
            cart = cart_service.get_cart()
            selected_id = (self.session.selected_product or {}).get("id")
            cart_ids = [it.product_id for it in cart.items]
            picked_cart_item = self._pick_entity_by_context(
                cart.items,
                "product_id",
                text,
                visible_ids=ctx_data.get("visible_cart_product_ids"),
            )
            if picked_cart_item:
                target_id = picked_cart_item.product_id
            elif selected_id and selected_id in cart_ids:
                target_id = selected_id
            elif cart.items:
                target_id = cart.items[-1].product_id
            else:
                target_id = selected_id
            if not target_id:
                msg = "Please choose a product first before updating quantity."
                self.last_response = msg
                return finalize({"action": "INFO", "message": msg, "speech_response": msg})
            if target_id in cart_ids:
                updated_cart = cart_service.update_quantity(target_id, qty)
            else:
                updated_cart = cart_service.add_item(target_id, quantity=qty)
            msg = (
                f"Updated quantity to {qty}. "
                f"Cart subtotal is ${updated_cart.subtotal:.2f} and total today is ${updated_cart.total_today:.2f}. "
                f"No payment has been made yet."
            )
            self.last_response = msg
            return finalize({
                "action": "TOTAL_SUMMARY",
                "cart": updated_cart.model_dump(),
                "message": msg,
                "speech_response": msg,
            }, refs=[target_id])

        if action_out.action == ConversationalAction.CHECK_TOTAL:
            cart = cart_service.get_cart()
            if not cart.items and self.session.selected_product:
                cart = cart_service.add_item(self.session.selected_product["id"], quantity=1)
            distinct_count = len(cart.items)
            item_lines = [
                f"- {it.product.title}: ${it.product.price:.2f} × {it.quantity} = ${it.item_total:.2f}"
                for it in cart.items
            ]
            summary_header = (
                f"You have {distinct_count} different product{'s' if distinct_count != 1 else ''} "
                f"and {cart.item_count} item{'s' if cart.item_count != 1 else ''} in your cart."
            )
            items_block = ("\n" + "\n".join(item_lines) + "\n") if item_lines else "\n"
            msg = (
                f"{summary_header}"
                f"{items_block}"
                f"Subtotal: ${cart.subtotal:.2f}\n"
                f"Shipping: ${cart.shipping_total:.2f}\n"
                f"Tax: ${cart.tax_total:.2f}\n"
                f"Your total today is ${cart.total_today:.2f}.\n"
                f"No payment has been made yet."
            )
            self.last_response = msg
            return finalize({
                "action": "TOTAL_SUMMARY",
                "cart": cart.model_dump(),
                "message": msg,
                "speech_response": (
                    f"{summary_header} Your total today is ${cart.total_today:.2f}. No payment has been made yet."
                ),
            })

        if action_out.action == ConversationalAction.PREPARE_CHECKOUT:
            cart = cart_service.get_cart()
            if not cart.items and current_view == "SAVED_ITEMS" and ctx_data.get("selected_saved_item_id"):
                added_res = await saved_service.add_saved_item_to_cart(ctx_data["selected_saved_item_id"])
                if added_res:
                    cart = cart_service.get_cart()
            if not cart.items and self.session.selected_product:
                cart = cart_service.add_item(self.session.selected_product["id"], quantity=1)
            if cart.items:
                review = confirmation_service.prepare_payment_review()
                item_lines = [
                    f"- {it.product.title} — ${it.product.price:.2f} × {it.quantity} = ${it.item_total:.2f}"
                    for it in cart.items
                ]
                msg = (
                    f"Purchase Review:\n"
                    + "\n".join(item_lines)
                    + f"\nSubtotal: ${review.item_subtotal:.2f}\n"
                    f"Shipping: ${review.shipping:.2f}\n"
                    f"Tax: ${review.tax:.2f}\n"
                    f"TOTAL: ${review.total_today:.2f}\n\n"
                    f"Say '{review.expected_phrase}' to continue."
                )
                self.last_response = msg
                return finalize({
                    "action": "PAYMENT_REVIEW_READY",
                    "review": review.model_dump(),
                    "message": msg,
                    "speech_response": f"Your total is ${review.total_today:.2f}. No payment has been made yet. Say {review.expected_phrase} to continue.",
                }, refs=[it.product_id for it in cart.items])
            msg = "Please choose a product first before continuing to payment review."
            self.last_response = msg
            return finalize({"action": "INFO", "message": msg, "speech_response": msg})

        # 6. Compare (strictly uses stored session products; asks clarification if ambiguous)
        if action_out.action == ConversationalAction.COMPARE:
            if any(w in text_lower for w in ("better", "recommend")) and "compare" not in text_lower and "vs" not in text_lower:
                if self.session.displayed_products:
                    top = self.session.displayed_products[0]
                    feats = top.get("documented_accessibility_features") or []
                    feat_str = f" It lists: {feats[0]}." if feats else ""
                    msg = f"{top['title']} (${top['price']:.2f} from {top['merchant']}) is ranked Best Match.{feat_str}"
                    self.session.last_discussed_product = top
                    self.last_response = msg
                    return finalize({"action": "RECOMMENDATION", "message": msg, "speech_response": msg}, refs=[top["id"]])
                msg = "Please search for products first so I can compare the options."
                self.last_response = msg
                return finalize({"action": "INFO", "message": msg, "speech_response": msg})

            pool = self.session.displayed_products or self.session.candidate_products
            if len(pool) < 2:
                msg = "Please search for products first so I have at least two options to compare."
                self.last_response = msg
                return finalize({"action": "INFO", "message": msg, "speech_response": msg})

            ref = resolve_product_references(text, self.session, expected_count=2, explicit_refs=action_out.references)
            if ref["ambiguous"]:
                self.session.pending_clarification = {"action": ConversationalAction.COMPARE.value}
                self.last_response = ref["question"]
                return finalize({
                    "action": "CLARIFICATION_NEEDED",
                    "needs_clarification": True,
                    "message": ref["question"],
                    "speech_response": ref["question"],
                })

            p1, p2 = ref["products"][0], ref["products"][1]
            comp_data = product_service.compare_products([p1["id"], p2["id"]])
            self.session.comparison_products = [p1, p2]
            self.session.last_discussed_product = p1
            msg = comp_data.get("summary", "Comparison ready.")
            self.last_response = msg
            return finalize({
                "action": "COMPARE",
                "comparison": comp_data,
                "message": msg,
                "speech_response": f"Option 1 is ${p1['price']:.2f}. Option 2 is ${p2['price']:.2f}. {comp_data.get('recommendation', '')}",
            }, refs=[p1["id"], p2["id"]])

        # 7. Select Product (strictly from active session; never searches or pays)
        if action_out.action == ConversationalAction.SELECT:
            ref = resolve_product_references(text, self.session, expected_count=1, explicit_refs=action_out.references)
            if ref["empty_pool"]:
                self.last_response = ref["question"]
                return finalize({"action": "INFO", "message": ref["question"], "speech_response": ref["question"]})
            if ref["ambiguous"]:
                self.session.pending_clarification = {"action": ConversationalAction.SELECT.value}
                self.last_response = ref["question"]
                return finalize({
                    "action": "CLARIFICATION_NEEDED",
                    "needs_clarification": True,
                    "message": ref["question"],
                    "speech_response": ref["question"],
                })

            chosen = ref["products"][0]
            self.session.selected_product = chosen
            self.session.last_discussed_product = chosen
            updated_cart = cart_service.add_item(chosen["id"], quantity=1)
            msg = (
                f"Selected {chosen['title']}.\n"
                f"Price: ${chosen['price']:.2f}\n"
                f"Cart items: {updated_cart.item_count} — Cart Total: ${updated_cart.total_today:.2f}\n\n"
                f"No payment has been made yet."
            )
            self.last_response = msg
            return finalize({
                "action": "PRODUCT_SELECTED",
                "product": chosen,
                "cart": updated_cart.model_dump(),
                "message": msg,
                "speech_response": f"Selected {chosen['title']} for ${chosen['price']:.2f}. Cart total is ${updated_cart.total_today:.2f}. No payment has been made.",
            }, refs=[chosen["id"]])

        # 8. Product Details & Attribute Inquiries (strictly cached session data; never invents or searches)
        if action_out.action == ConversationalAction.PRODUCT_DETAILS:
            pool = self.session.displayed_products or self.session.candidate_products
            if not pool:
                msg = "Please search for products first before asking for product details."
                self.last_response = msg
                return finalize({"action": "INFO", "message": msg, "speech_response": msg})

            is_price_inquiry = bool(
                re.search(r"\b(?:which(?:\s+one)?\s+is\s+(?:the\s+)?(?:cheaper|cheapest|lowest|most\s+expensive|priciest|pricier)|how\s+much\s+is)\b", text_lower)
            )
            is_attr_q = (
                not is_price_inquiry
                and bool(
                    re.search(
                        r"\b(?:which(?:\s+one)?\s+(?:is|has)|is it |is the |does it have|does the |do they have|"
                        r"what is the weight|how heavy|lightest|waterproof|battery|warranty|material|reviews?|rating|highest rated)\b",
                        text_lower,
                    )
                )
            )
            has_explicit_target = bool(
                re.search(r"\b(?:first|second|third|fourth|last|1st|2nd|3rd|option|cheapest|cheaper|expensive|selected|other)\b", text_lower)
                or action_out.references
            )
            if is_attr_q and not has_explicit_target:
                target_pool = pool[:3]
                if self.session.selected_product or self.session.last_discussed_product:
                    if not re.search(r"\bwhich(?:\s+one)?\b", text_lower):
                        target_pool = [self.session.selected_product or self.session.last_discussed_product]
                attr_ans = product_service.answer_attribute_question(text, target_pool)
                if not attr_ans["found"] or len(target_pool) == 1 or re.search(r"\bwhich(?:\s+one)?\b", text_lower):
                    self.last_response = attr_ans["message"]
                    return finalize({
                        "action": "ATTRIBUTE_INQUIRY",
                        "found": attr_ans["found"],
                        "message": attr_ans["message"],
                        "speech_response": attr_ans["speech_response"],
                    }, refs=[p["id"] for p in target_pool])

            ref = resolve_product_references(text, self.session, expected_count=1, explicit_refs=action_out.references)
            if ref["ambiguous"]:
                self.session.pending_clarification = {"action": ConversationalAction.PRODUCT_DETAILS.value}
                self.last_response = ref["question"]
                return finalize({
                    "action": "CLARIFICATION_NEEDED",
                    "needs_clarification": True,
                    "message": ref["question"],
                    "speech_response": ref["question"],
                })

            chosen = ref["products"][0]
            self.session.last_discussed_product = chosen
            if is_price_inquiry:
                msg = f"{chosen['title']} is ${chosen['price']:.2f} from {chosen['merchant']}."
                self.last_response = msg
                return finalize({
                    "action": "PRODUCT_DETAILS",
                    "product": chosen,
                    "message": msg,
                    "speech_response": msg,
                }, refs=[chosen["id"]])
            if is_attr_q:
                attr_ans = product_service.answer_attribute_question(text, [chosen])
                self.last_response = attr_ans["message"]
                return finalize({
                    "action": "ATTRIBUTE_INQUIRY",
                    "found": attr_ans["found"],
                    "product": chosen,
                    "message": attr_ans["message"],
                    "speech_response": attr_ans["speech_response"],
                }, refs=[chosen["id"]])

            feats = "; ".join(chosen.get("documented_accessibility_features", [])[:2])
            feat_text = f" Features: {feats}." if feats else ""
            desc = str(chosen.get("description") or "").strip()
            desc_snippet = f" {desc[:180]}" if desc and desc.lower() not in chosen["title"].lower() else ""
            msg = f"{chosen['title']} is ${chosen['price']:.2f} from {chosen['merchant']}.{feat_text}{desc_snippet}".strip()
            self.last_response = msg
            return finalize({
                "action": "PRODUCT_DETAILS",
                "product": chosen,
                "message": msg,
                "speech_response": msg,
            }, refs=[chosen["id"]])

        # 9. Sort Results (purely in-session on cached candidates)
        if action_out.action == ConversationalAction.SORT_RESULTS:
            sort_pref = action_out.sort_preference or "price_asc"
            pool_models = [m for m in (_to_product_model(d) for d in (self.session.candidate_products or self.session.displayed_products)) if m]
            if not pool_models:
                msg = "Please search for products first before sorting."
                self.last_response = msg
                return finalize({"action": "INFO", "message": msg, "speech_response": msg})
            if self.session.structured_search_intent:
                updated_intent = self.session.structured_search_intent.model_copy(deep=True)
            else:
                updated_intent = extract_search_intent_rules(self.session.original_query or pool_models[0].title, last_intent=None)
            updated_intent.sort_preference = sort_pref
            updated_intent.constraints = build_typed_constraints(updated_intent)
            self.session.sync_from_intent(updated_intent)
            ranked, _, _ = score_and_filter_candidates(pool_models, updated_intent, enforce_budget=True)
            page_limit = max(DEFAULT_DISPLAY_LIMIT, len(self.session.displayed_products) or DEFAULT_DISPLAY_LIMIT)
            top_items = ranked[:page_limit]
            self.session.candidate_products = [p.model_dump() for p in ranked]
            self.session.displayed_products = [p.model_dump() for p in top_items]
            self.session.has_more = len(ranked) > len(top_items)
            self.session.total_available = len(ranked)
            msg = f"Sorted results ({len(top_items)} shown):\n" + "\n".join(
                [f"{i+1}. {p.title} — ${p.price:.2f}" for i, p in enumerate(top_items)]
            )
            self.last_response = msg
            return finalize({
                "action": "SEARCH_RESULTS",
                "count": len(top_items),
                "products": list(self.session.displayed_products),
                "has_more": self.session.has_more,
                "total_candidates": len(ranked),
                "source": "Cached Session Candidates",
                "message": msg,
                "speech_response": msg,
            })

        # 10. Show More Results (extends current displayed list inside the SAME active search)
        if action_out.action == ConversationalAction.SHOW_MORE:
            return await self.show_more_results(
                user_text=text,
                action_out=action_out,
                provider_label=provider_label,
                turn_ctx=turn_ctx,
            )

        # 10b. Pagination (NEXT_OPTION / PREVIOUS_OPTION)
        if action_out.action in (ConversationalAction.NEXT_OPTION, ConversationalAction.PREVIOUS_OPTION):
            candidates = self.session.candidate_products or [p.model_dump() for p in product_service.last_search_candidates]
            if len(candidates) > DEFAULT_DISPLAY_LIMIT:
                delta = DEFAULT_DISPLAY_LIMIT if action_out.action == ConversationalAction.NEXT_OPTION else -DEFAULT_DISPLAY_LIMIT
                self.session.candidate_offset = (self.session.candidate_offset + delta) % len(candidates)
                sliced = (candidates[self.session.candidate_offset:] + candidates[:self.session.candidate_offset])[:DEFAULT_DISPLAY_LIMIT]
                self.session.displayed_products = sliced
                msg = f"Showing options from your current search: {sliced[0]['title']} (${sliced[0]['price']:.2f})."
                self.last_response = msg
                return finalize({
                    "action": "SEARCH_RESULTS",
                    "count": len(sliced),
                    "products": sliced,
                    "source": "Cached Session Candidates",
                    "message": msg,
                    "speech_response": msg,
                }, refs=[p["id"] for p in sliced])
            elif self.session.displayed_products:
                rotated = (
                    self.session.displayed_products[1:] + self.session.displayed_products[:1]
                    if action_out.action == ConversationalAction.NEXT_OPTION
                    else self.session.displayed_products[-1:] + self.session.displayed_products[:-1]
                )
                self.session.displayed_products = rotated
                msg = f"Another option is {rotated[0]['title']} for ${rotated[0]['price']:.2f} from {rotated[0]['merchant']}."
                self.last_response = msg
                return finalize({
                    "action": "SEARCH_RESULTS",
                    "count": len(rotated),
                    "products": rotated,
                    "source": "Cached Session Candidates",
                    "message": msg,
                    "speech_response": msg,
                }, refs=[rotated[0]["id"]])

        # 11. Cheaper Alternative — Generic Semantic Constraint (never unrelated cheap product)
        if action_out.action == ConversationalAction.CHEAPER_ALTERNATIVE:
            pool = self.session.displayed_products or self.session.candidate_products
            if not pool:
                msg = "Please search for products first so I can look for a cheaper matching option."
                self.last_response = msg
                return finalize({"action": "INFO", "message": msg, "speech_response": msg})

            ref_prod = pool[0]
            if any(w in text_lower for w in ("second", "third", "selected", "2nd", "3rd", "2", "3")):
                ref = resolve_product_references(text, self.session, expected_count=1, explicit_refs=action_out.references)
                if not ref["ambiguous"] and ref["products"]:
                    ref_prod = ref["products"][0]

            ref_price = float(ref_prod["price"])
            inv_intent = self.session.build_invariant_cheaper_intent(ref_price)
            if inv_intent is None and ref_price > 1.0:
                seed_intent = extract_search_intent_rules(self.session.original_query or ref_prod.get("title", ""), last_intent=None)
                seed_intent.max_price = max(1.0, round(ref_price - 0.01, 2))
                seed_intent.sort_preference = "price_asc"
                seed_intent.constraints = build_typed_constraints(seed_intent)
                inv_intent = seed_intent

            # Check cached candidates under invariant semantic constraints first
            alt_product: Optional[Product] = None
            alt_id = ref_prod.get("cheaper_alternative_id")
            if alt_id:
                cand_by_id = product_service.get_product_by_id(alt_id)
                if cand_by_id and cand_by_id.price < ref_price:
                    if inv_intent:
                        valid_alt, _, _ = score_and_filter_candidates([cand_by_id], inv_intent, enforce_budget=True)
                        alt_product = valid_alt[0] if valid_alt else None
                    else:
                        alt_product = cand_by_id

            if not alt_product and inv_intent:
                cached_pool = [
                    p for p in (
                        [_to_product_model(d) for d in self.session.candidate_products]
                        or list(product_service.last_search_candidates)
                    )
                    if p is not None and p.id != ref_prod.get("id") and p.price < ref_price
                ]
                valid_cached, _, _ = score_and_filter_candidates(cached_pool, inv_intent, enforce_budget=True)
                if valid_cached:
                    alt_product = min(valid_cached, key=lambda p: p.price)

            c3_called = False
            if alt_product:
                savings = round(ref_price - alt_product.price, 2)
                alt_dict = alt_product.model_dump()
                self.session.alternative_product = alt_dict
                msg = f"I found a similar option for ${savings:.2f} less: {alt_product.title} (${alt_product.price:.2f})."
                self.last_response = msg
                return finalize({
                    "action": "CHEAPER_ALTERNATIVE_FOUND",
                    "alternative_product": alt_dict,
                    "original_product": ref_prod,
                    "savings": savings,
                    "message": msg,
                    "speech_response": msg,
                }, channel3_called=False, refs=[ref_prod["id"], alt_product.id])

            # Fallback: query Channel3 using active structured intent + lower price bound
            if inv_intent and inv_intent.max_price >= 1.0:
                req_gen = self.session.search_generation
                c3_called = True
                search_res = await product_service.search_products(
                    query=inv_intent.search_query,
                    budget_limit=inv_intent.max_price,
                    min_price=inv_intent.min_price,
                    requirements=inv_intent.features,
                    intent=inv_intent,
                )
                if req_gen != self.session.search_generation:
                    return {"action": "STALE_DISCARDED", "stale": True, "search_generation": self.session.search_generation}
                refined_products = [
                    p for p in search_res.get("products", [])
                    if p.price < ref_price and p.id != ref_prod.get("id")
                ]
                if refined_products:
                    alt_prod = min(refined_products, key=lambda p: p.price)
                    savings = max(0.01, round(ref_price - alt_prod.price, 2))
                    alt_dict = alt_prod.model_dump()
                    self.session.alternative_product = alt_dict
                    msg = f"I found a similar option for ${savings:.2f} less: {alt_prod.title} (${alt_prod.price:.2f})."
                    self.last_response = msg
                    return finalize({
                        "action": "CHEAPER_ALTERNATIVE_FOUND",
                        "alternative_product": alt_dict,
                        "original_product": ref_prod,
                        "savings": savings,
                        "message": msg,
                        "speech_response": msg,
                    }, channel3_called=c3_called, refs=[ref_prod["id"], alt_prod.id])

            msg = "I couldn't find a cheaper matching option than what is already shown. Your current results are still active."
            self.last_response = msg
            return finalize({
                "action": "INFO",
                "preserve_active_products": True,
                "count": len(self.session.displayed_products),
                "products": list(self.session.displayed_products),
                "message": msg,
                "speech_response": msg,
            }, channel3_called=c3_called, refs=[ref_prod["id"]])

        # 12. Other Alternative ("another option", "another brand", "different color", "something similar")
        if action_out.action == ConversationalAction.OTHER_ALTERNATIVE:
            if not self.session.structured_search_intent:
                active_pool = self.session.displayed_products or self.session.candidate_products
                if not active_pool:
                    msg = "Please tell me what product you're looking for first."
                    self.last_response = msg
                    return finalize({"action": "INFO", "message": msg, "speech_response": msg})
                synth = extract_search_intent_rules(self.session.original_query or active_pool[0].get("title", ""), last_intent=None)
                self.session.sync_from_intent(synth)

            if any(p in text_lower for p in ("another brand", "different brand", "other brand")):
                refined = extract_search_intent_rules(
                    text,
                    last_intent=self.session.structured_search_intent,
                    shown_brands=self.session.shown_brands(),
                )
                return await self._run_session_search(text, refined, action_out, is_new_search=False, provider_label=provider_label, turn_ctx=turn_ctx)

            if "different color" in text_lower or "other color" in text_lower:
                msg = "Which color would you like to see instead?"
                self.session.pending_clarification = {"action": ConversationalAction.FILTER_RESULTS.value}
                self.last_response = msg
                return finalize({"action": "CLARIFICATION_NEEDED", "needs_clarification": True, "message": msg, "speech_response": msg})

            # Otherwise cycle remaining candidates from current generation without calling Channel3 unless exhausted
            candidates = self.session.candidate_products or [p.model_dump() for p in product_service.last_search_candidates]
            if len(candidates) > DEFAULT_DISPLAY_LIMIT:
                self.session.candidate_offset = (self.session.candidate_offset + DEFAULT_DISPLAY_LIMIT) % len(candidates)
                sliced = (candidates[self.session.candidate_offset:] + candidates[:self.session.candidate_offset])[:DEFAULT_DISPLAY_LIMIT]
                self.session.displayed_products = sliced
                msg = f"Here are other matching options from your search: {sliced[0]['title']} (${sliced[0]['price']:.2f})."
                self.last_response = msg
                return finalize({
                    "action": "SEARCH_RESULTS",
                    "count": len(sliced),
                    "products": sliced,
                    "source": "Cached Session Candidates",
                    "message": msg,
                    "speech_response": msg,
                }, refs=[p["id"] for p in sliced])
            elif self.session.displayed_products:
                rotated = self.session.displayed_products[1:] + self.session.displayed_products[:1]
                self.session.displayed_products = rotated
                msg = f"Another option is {rotated[0]['title']} for ${rotated[0]['price']:.2f} from {rotated[0]['merchant']}."
                self.last_response = msg
                return finalize({
                    "action": "SEARCH_RESULTS",
                    "count": len(rotated),
                    "products": rotated,
                    "source": "Cached Session Candidates",
                    "message": msg,
                    "speech_response": msg,
                }, refs=[rotated[0]["id"]])

        # 13. Refinement / Filter Results (preserves unrelated active constraints)
        if action_out.action in (ConversationalAction.FILTER_RESULTS, ConversationalAction.REFINE_SEARCH):
            if not self.session.structured_search_intent:
                active_pool = self.session.displayed_products or self.session.candidate_products
                if not active_pool:
                    msg = "Please tell me what product to search for before applying filters."
                    self.last_response = msg
                    return finalize({"action": "CLARIFICATION_NEEDED", "needs_clarification": True, "message": msg, "speech_response": msg})
                base_intent = extract_search_intent_rules(self.session.original_query or active_pool[0].get("title", ""), last_intent=None)
            else:
                base_intent = self.session.structured_search_intent.model_copy(deep=True)
            base_intent.raw_query = text
            base_intent.is_followup = True
            if action_out.max_price is not None:
                base_intent.max_price = action_out.max_price
            if action_out.min_price is not None:
                base_intent.min_price = action_out.min_price
            if action_out.color:
                base_intent.color = action_out.color
            if action_out.size:
                base_intent.size = action_out.size
            if action_out.compatibility:
                base_intent.compatibility = action_out.compatibility
            if action_out.features:
                for feat in action_out.features:
                    if feat not in base_intent.features:
                        base_intent.features.append(feat)
            if action_out.sort_preference:
                base_intent.sort_preference = action_out.sort_preference

            if action_out.constraint_updates.get("cheaper_list") or ("cheap" in text_lower and self.session.displayed_products):
                top_price = max(p["price"] for p in self.session.displayed_products) if self.session.displayed_products else None
                if top_price is not None and (base_intent.max_price is None or base_intent.max_price >= top_price):
                    base_intent.max_price = round(max(1.0, top_price - 0.01), 2)
                base_intent.sort_preference = "price_asc"

            base_intent.broaden_queries = build_broadened_queries(base_intent)
            base_intent.constraints = build_typed_constraints(base_intent)
            return await self._run_session_search(text, base_intent, action_out, is_new_search=False, provider_label=provider_label, turn_ctx=turn_ctx)

        # 14. Unknown / Unclear Conversational Message (NEVER calls Channel3)
        if action_out.action in (ConversationalAction.UNKNOWN, ConversationalAction.CLARIFICATION_NEEDED):
            msg = action_out.clarification_question or "Could you clarify what you'd like to do — search for a new product, compare options, or pick an option number?"
            self.last_response = msg
            return finalize({
                "action": "CLARIFICATION_NEEDED",
                "needs_clarification": True,
                "message": msg,
                "speech_response": msg,
            })

        # 15. New Search -> creates new generation, clears old context, searches Channel3
        new_intent = self._build_intent_from_action(text, action_out)
        return await self._run_session_search(text, new_intent, action_out, is_new_search=True, provider_label=provider_label, turn_ctx=turn_ctx)

    def _build_intent_from_action(self, user_text: str, action_out: StructuredActionOutput) -> StructuredSearchIntent:
        rule_intent = extract_search_intent_rules(user_text, last_intent=None)
        search_q = (action_out.search_query or "").strip() or rule_intent.search_query
        pt = (action_out.product_type or "").strip() or rule_intent.product_type
        if pt and not action_out.starts_new_search and pt.lower() not in search_q.lower():
            search_q = f"{search_q} {pt}".strip()

        merged_feats = list(dict.fromkeys(rule_intent.features + [str(f).lower() for f in action_out.features if f]))
        intent = StructuredSearchIntent(
            raw_query=user_text,
            search_query=search_q,
            product_type=pt,
            brand=action_out.brand or rule_intent.brand,
            character_or_franchise=action_out.character_or_franchise or rule_intent.character_or_franchise,
            model=action_out.model or rule_intent.model,
            category=action_out.category or rule_intent.category,
            max_price=action_out.max_price if action_out.max_price is not None else rule_intent.max_price,
            min_price=action_out.min_price if action_out.min_price is not None else rule_intent.min_price,
            color=(action_out.color.lower() if action_out.color else None) or rule_intent.color,
            size=action_out.size or rule_intent.size,
            features=merged_feats,
            compatibility=action_out.compatibility or rule_intent.compatibility,
            recipient_or_use_case=action_out.recipient_or_use_case or rule_intent.recipient_or_use_case,
            sort_preference=action_out.sort_preference or rule_intent.sort_preference,
            is_followup=False,
        )
        intent.broaden_queries = build_broadened_queries(intent)
        intent.constraints = build_typed_constraints(intent)
        return intent

    async def execute_structured_search(
        self,
        user_text: str,
        intent: Optional[StructuredSearchIntent] = None,
    ) -> Dict[str, Any]:
        """Backwards-compatible entry point for direct structured search calls."""
        active = intent or extract_search_intent_rules(
            user_text,
            last_intent=self.session.structured_search_intent,
            shown_brands=self.session.shown_brands(),
        )
        act_enum = ConversationalAction.REFINE_SEARCH if active.is_followup else ConversationalAction.NEW_SEARCH
        action_out = StructuredActionOutput(
            action=act_enum,
            starts_new_search=not active.is_followup,
            search_query=active.search_query,
            product_type=active.product_type,
            brand=active.brand,
            model=active.model,
            character_or_franchise=active.character_or_franchise,
            max_price=active.max_price,
            min_price=active.min_price,
            color=active.color,
            features=active.features,
            compatibility=active.compatibility,
            recipient_or_use_case=active.recipient_or_use_case,
            sort_preference=active.sort_preference,
        )
        return await self._run_session_search(user_text, active, action_out, is_new_search=not active.is_followup)

    async def _run_session_search(
        self,
        user_text: str,
        active_intent: StructuredSearchIntent,
        action_out: StructuredActionOutput,
        is_new_search: bool,
        provider_label: str = "mock",
        turn_ctx: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        prev_action = self.session.last_action
        prev_gen = self.session.search_generation
        input_mode = (turn_ctx or {}).get("input_mode", "text")

        def finish(payload: Dict[str, Any], channel3_called: bool) -> Dict[str, Any]:
            payload.setdefault("provider", provider_label)
            self.session.last_action = payload.get("action", action_out.action.value)
            self.session.last_user_message = user_text
            self.session.pending_clarification = None
            self._sync_cart_snapshot()
            self._attach_session_metadata(
                payload,
                action_out,
                channel3_called=channel3_called,
                referenced_ids=[p.get("id") for p in payload.get("products", [])],
                input_mode=input_mode,
            )
            self._log_turn(
                user_text,
                prev_action,
                prev_gen,
                action_out,
                channel3_called=channel3_called,
                referenced_ids=[p.get("id") for p in payload.get("products", [])],
                turn_ctx=turn_ctx,
                resolved_action=payload.get("action"),
            )
            return payload

        prev_displayed = list(self.session.displayed_products)
        prev_candidates = list(self.session.candidate_products)
        prev_intent = self.session.structured_search_intent.model_copy(deep=True) if self.session.structured_search_intent else None
        prev_has_more = self.session.has_more
        prev_total_available = self.session.total_available

        if is_new_search:
            req_gen = self.session.start_new_generation(user_text, active_intent)
        else:
            req_gen = self.session.search_generation
            self.session.sync_from_intent(active_intent)

        # Follow-up refinements check cached session candidates first
        if not is_new_search and product_service.last_search_candidates:
            cached_matches = product_service.filter_cached_candidates(intent=active_intent)
            need_fresh_fetch = bool(
                (active_intent.color and len(cached_matches) < 2)
                or (active_intent.exclude_brands and len(cached_matches) < 2)
                or (active_intent.min_price is not None)
                or (len(cached_matches) == 0)
            )
            if cached_matches and not need_fresh_fetch:
                if req_gen != self.session.search_generation:
                    return {"action": "STALE_DISCARDED", "stale": True, "search_generation": self.session.search_generation}
                top_cached = cached_matches[:DEFAULT_DISPLAY_LIMIT]
                self.session.candidate_products = [p.model_dump() for p in cached_matches]
                self.session.displayed_products = [p.model_dump() for p in top_cached]
                self.session.has_more = len(cached_matches) > len(top_cached)
                self.session.total_available = len(cached_matches)
                msg = f"Filtered current results ({len(top_cached)} shown):\n" + "\n".join(
                    [f"{i+1}. {p.title} — ${p.price:.2f} ({p.ranking_badge or 'OPTION'})" for i, p in enumerate(top_cached)]
                )
                self.last_response = msg
                return finish({
                    "action": "SEARCH_RESULTS",
                    "count": len(top_cached),
                    "products": list(self.session.displayed_products),
                    "total_candidates": len(cached_matches),
                    "has_more": self.session.has_more,
                    "product_mode": product_service.get_mode_status().get("product_mode"),
                    "source": "Cached Session Candidates",
                    "extracted_requirements": active_intent.model_dump(),
                    "message": msg,
                    "speech_response": f"Showing {len(top_cached)} filtered options. Top match is {top_cached[0].title} for ${top_cached[0].price:.2f}.",
                }, channel3_called=False)

        search_res = await product_service.search_products(
            query=active_intent.search_query,
            budget_limit=active_intent.max_price,
            min_price=active_intent.min_price,
            requirements=active_intent.features,
            intent=active_intent,
            display_limit=DEFAULT_DISPLAY_LIMIT,
        )

        # Discard stale async search response if a newer search generation was started
        if req_gen != self.session.search_generation:
            logger.info("[SessionDebug] Discarding stale search response from gen=%d (active gen=%d)", req_gen, self.session.search_generation)
            return {
                "action": "STALE_DISCARDED",
                "stale": True,
                "search_generation": self.session.search_generation,
            }

        def preserve_previous_results(info_msg: str, channel3_called: bool) -> Dict[str, Any]:
            self.session.displayed_products = prev_displayed
            self.session.candidate_products = prev_candidates
            if prev_intent:
                self.session.sync_from_intent(prev_intent)
            self.session.has_more = prev_has_more
            self.session.total_available = prev_total_available
            self.last_response = info_msg
            return finish({
                "action": "INFO",
                "preserve_active_products": True,
                "count": len(prev_displayed),
                "products": list(prev_displayed),
                "total_candidates": prev_total_available or len(prev_displayed),
                "has_more": prev_has_more,
                "message": info_msg,
                "speech_response": info_msg,
            }, channel3_called=channel3_called)

        if search_res.get("error"):
            if not is_new_search and prev_displayed:
                return preserve_previous_results(
                    "I had trouble updating that filter right now, so I'm keeping your current results active.",
                    channel3_called=True,
                )
            err_msg = "I'm having trouble searching right now.\nPlease try again."
            self.last_response = err_msg
            self.session.displayed_products = []
            self.session.has_more = False
            self.session.total_available = 0
            return finish({
                "action": "SEARCH_ERROR",
                "error": True,
                "count": 0,
                "products": [],
                "message": err_msg,
                "speech_response": "I'm having trouble searching right now. Please try again.",
            }, channel3_called=True)

        all_candidates = list(product_service.last_search_candidates or search_res.get("products", []))
        self.session.candidate_products = [p.model_dump() for p in all_candidates]
        shown = list(search_res.get("products", [])[:DEFAULT_DISPLAY_LIMIT])
        self.session.displayed_products = [p.model_dump() if hasattr(p, "model_dump") else p for p in shown]
        self.session.total_available = len(all_candidates)
        self.session.has_more = len(all_candidates) > len(shown)

        if is_new_search and user_text.strip():
            saved_service.record_search_history(
                search_id=self.session.search_id,
                query=self.session.original_query or user_text,
                display_query=self.session.display_query or user_text,
                result_count=len(all_candidates),
                structured_intent=active_intent.model_dump() if active_intent else {},
                filters=dict(self.session.active_filters or {}),
                sort=active_intent.sort_preference if active_intent else None,
            )

        if not shown and search_res.get("budget_exceeded") and active_intent.max_price is not None:
            above_prods = [
                p.model_dump() if hasattr(p, "model_dump") else p
                for p in (search_res.get("above_budget_products") or [])[:DEFAULT_DISPLAY_LIMIT]
            ]
            budget_disp = (
                f"${int(active_intent.max_price)}"
                if float(active_intent.max_price).is_integer()
                else f"${active_intent.max_price:.2f}"
            )
            if not is_new_search and prev_displayed:
                return preserve_previous_results(
                    f"No matching options were found under {budget_disp}. Keeping your {len(prev_displayed)} active results.",
                    channel3_called=True,
                )
            msg = f"I found matching products, but none under {budget_disp}."
            self.last_response = msg
            return finish({
                "action": "NO_RESULTS",
                "budget_exceeded": True,
                "budget_limit": active_intent.max_price,
                "above_budget_products": above_prods,
                "count": 0,
                "products": [],
                "message": msg,
                "speech_response": msg,
            }, channel3_called=True)

        if not shown:
            if not is_new_search and prev_displayed:
                return preserve_previous_results(
                    f"No options in your current search matched '{user_text}'. Keeping your {len(prev_displayed)} active results.",
                    channel3_called=True,
                )
            no_res_msg = "I couldn't find a good match.\n\nNo matching products were found in the available product catalog. Try changing your budget or product requirements."
            self.last_response = no_res_msg
            return finish({
                "action": "NO_RESULTS",
                "count": 0,
                "products": [],
                "message": no_res_msg,
                "speech_response": "I couldn't find a good match. Try changing your budget or product requirements.",
            }, channel3_called=True)

        lines = []
        for i, p in enumerate(shown):
            badge = p.ranking_badge or f"OPTION {i+1}"
            feat_note = ""
            if p.documented_accessibility_features:
                feat_note = f" — This product lists: {p.documented_accessibility_features[0]}"
            lines.append(f"{badge}: {p.title} (${p.price:.2f} from {p.merchant}){feat_note}")

        more_hint = f" ({len(all_candidates) - len(shown)} more available)" if self.session.has_more else ""
        msg = f"Found {len(shown)} strong choice{'s' if len(shown) != 1 else ''}{more_hint}:\n" + "\n".join(lines)
        speech_msg = f"Found {len(shown)} options. Best match is {shown[0].title} for ${shown[0].price:.2f} from {shown[0].merchant}."
        self.last_response = msg
        return finish({
            "action": "SEARCH_RESULTS",
            "count": len(shown),
            "total_candidates": len(all_candidates),
            "has_more": self.session.has_more,
            "products": list(self.session.displayed_products),
            "product_mode": search_res.get("product_mode"),
            "source": search_res.get("source"),
            "extracted_requirements": active_intent.model_dump(),
            "message": msg,
            "speech_response": speech_msg,
        }, channel3_called=True)

    async def show_more_results(
        self,
        user_text: str = "Show more",
        action_out: Optional[StructuredActionOutput] = None,
        provider_label: str = "mock",
        turn_ctx: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Appends additional high-quality results from the SAME active search without resetting generation."""
        act = action_out or StructuredActionOutput(action=ConversationalAction.SHOW_MORE)
        prev_action = self.session.last_action
        prev_gen = self.session.search_generation
        input_mode = (turn_ctx or {}).get("input_mode", "text")

        def finish_more(payload: Dict[str, Any], channel3_called: bool = False, refs: Optional[List[str]] = None) -> Dict[str, Any]:
            self.session.last_action = payload.get("action", "SEARCH_RESULTS")
            self.session.last_user_message = user_text
            self._attach_session_metadata(
                payload,
                act,
                channel3_called=channel3_called,
                referenced_ids=refs,
                input_mode=input_mode,
            )
            self._log_turn(
                user_text,
                prev_action,
                prev_gen,
                act,
                channel3_called=channel3_called,
                referenced_ids=refs,
                turn_ctx=turn_ctx,
                resolved_action=payload.get("action"),
            )
            return payload

        if not self.session.displayed_products and not self.session.candidate_products:
            msg = "Please run a product search first before asking for more results."
            self.last_response = msg
            return finish_more({"action": "INFO", "message": msg, "speech_response": msg}, channel3_called=False)

        shown_ids = {p.get("id") for p in self.session.displayed_products if p.get("id")}
        remaining = [
            p for p in self.session.candidate_products
            if p.get("id") and p.get("id") not in shown_ids
        ]

        c3_called = False
        if not remaining and self.session.structured_search_intent:
            req_gen = self.session.search_generation
            expanded_limit = len(self.session.displayed_products) + DEFAULT_DISPLAY_LIMIT
            c3_called = True
            search_res = await product_service.search_products(
                query=self.session.structured_search_intent.search_query,
                budget_limit=self.session.structured_search_intent.max_price,
                min_price=self.session.structured_search_intent.min_price,
                requirements=self.session.structured_search_intent.features,
                intent=self.session.structured_search_intent,
                display_limit=expanded_limit,
                force_refresh=True,
            )
            if req_gen != self.session.search_generation:
                return {"action": "STALE_DISCARDED", "stale": True, "search_generation": self.session.search_generation}
            all_cands = [p.model_dump() for p in (product_service.last_search_candidates or search_res.get("products", []))]
            for cand in all_cands:
                if cand.get("id") and cand.get("id") not in {c.get("id") for c in self.session.candidate_products}:
                    self.session.candidate_products.append(cand)
            remaining = [
                p for p in self.session.candidate_products
                if p.get("id") and p.get("id") not in shown_ids
            ]

        batch = remaining[:DEFAULT_DISPLAY_LIMIT]
        if not batch:
            self.session.has_more = False
            msg = "No more matching results are available for this search."
            self.last_response = msg
            return finish_more(
                {
                    "action": "SEARCH_RESULTS",
                    "count": len(self.session.displayed_products),
                    "products": list(self.session.displayed_products),
                    "added_count": 0,
                    "has_more": False,
                    "total_candidates": len(self.session.candidate_products),
                    "message": msg,
                    "speech_response": msg,
                },
                channel3_called=c3_called,
            )

        self.session.displayed_products.extend(batch)
        self.session.total_available = len(self.session.candidate_products)
        self.session.has_more = len(self.session.displayed_products) < len(self.session.candidate_products)
        msg = f"Showing {len(batch)} more option{'s' if len(batch) != 1 else ''} ({len(self.session.displayed_products)} total shown)."
        self.last_response = msg
        return finish_more(
            {
                "action": "SEARCH_RESULTS",
                "count": len(self.session.displayed_products),
                "added_count": len(batch),
                "products": list(self.session.displayed_products),
                "has_more": self.session.has_more,
                "total_candidates": len(self.session.candidate_products),
                "provider": provider_label,
                "message": msg,
                "speech_response": msg,
            },
            channel3_called=c3_called,
            refs=[p.get("id") for p in batch if p.get("id")],
        )

    def sync_external_search_results(
        self,
        query: str,
        intent: StructuredSearchIntent,
        search_res: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Synchronizes direct /api/products/search calls with the single authoritative ActiveSearchSession
        so initial page loads and follow-ups share exact card ordering and generation tracking.
        """
        self.session.start_new_generation(query, intent)
        all_candidates = list(product_service.last_search_candidates or search_res.get("products", []))
        self.session.candidate_products = [p.model_dump() if hasattr(p, "model_dump") else p for p in all_candidates]
        shown = list(search_res.get("products", []))
        self.session.displayed_products = [p.model_dump() if hasattr(p, "model_dump") else p for p in shown]
        self.session.total_available = len(all_candidates)
        self.session.has_more = len(all_candidates) > len(shown)
        if query.strip() and not search_res.get("error"):
            saved_service.record_search_history(
                search_id=self.session.search_id,
                query=query,
                display_query=self.session.display_query or query,
                result_count=len(all_candidates),
                structured_intent=intent.model_dump() if intent else {},
                filters=dict(self.session.active_filters or {}),
                sort=intent.sort_preference if intent else None,
            )
        return {
            "search_id": self.session.search_id,
            "search_generation": self.session.search_generation,
            "has_more": self.session.has_more,
            "total_candidates": len(all_candidates),
        }

    async def _rerun_structured_query(
        self,
        original_query: str,
        intent_dict: Dict[str, Any],
        sort: Optional[str],
        provider_label: str,
    ) -> Dict[str, Any]:
        """Re-runs a stored query + structured intent live against Channel3/ProductService."""
        base_intent = (
            StructuredSearchIntent(**intent_dict)
            if intent_dict
            else extract_search_intent_rules(original_query, last_intent=None)
        )
        if sort:
            base_intent.sort_preference = sort
        base_intent.is_followup = False
        base_intent.broaden_queries = build_broadened_queries(base_intent)
        base_intent.constraints = build_typed_constraints(base_intent)

        action_out = StructuredActionOutput(
            action=ConversationalAction.NEW_SEARCH,
            starts_new_search=True,
            search_query=base_intent.search_query,
            product_type=base_intent.product_type,
            brand=base_intent.brand,
            model=base_intent.model,
            character_or_franchise=base_intent.character_or_franchise,
            max_price=base_intent.max_price,
            min_price=base_intent.min_price,
            color=base_intent.color,
            size=base_intent.size,
            features=list(base_intent.features),
            compatibility=base_intent.compatibility,
            recipient_or_use_case=base_intent.recipient_or_use_case,
            sort_preference=base_intent.sort_preference,
        )
        return await self._run_session_search(
            original_query,
            base_intent,
            action_out,
            is_new_search=True,
            provider_label=provider_label,
        )

    async def run_saved_search_by_id(self, saved_search_id: str) -> Dict[str, Any]:
        """Re-runs a SavedSearch live against Channel3/ProductService so prices and availability are fresh."""
        saved = saved_service.get_saved_search(saved_search_id)
        if not saved:
            raise ValueError("Saved search not found.")
        res = await self._rerun_structured_query(
            original_query=saved.original_query,
            intent_dict=dict(saved.structured_intent or {}),
            sort=saved.sort,
            provider_label="saved_search_rerun",
        )
        res["reopened_saved_search"] = saved.model_dump()
        res["speech_response"] = "Search reopened. " + res.get("speech_response", "")
        return res

    async def run_search_history_by_id(self, history_id: str) -> Dict[str, Any]:
        """Re-runs a Recent Search entry live against Channel3/ProductService as a new ActiveSearchSession."""
        entry = saved_service.get_search_history_entry(history_id)
        if not entry:
            raise ValueError("Recent search entry not found.")
        res = await self._rerun_structured_query(
            original_query=entry.query,
            intent_dict=dict(entry.structured_intent or {}),
            sort=entry.sort,
            provider_label="recent_search_rerun",
        )
        res["reopened_history_entry"] = entry.model_dump()
        return res


class LLMAIService:
    """
    Real LLM-backed AI Service (Google Gemini / OpenAI):
    - Uses structured action classification + validation over the authoritative ShoppingSession.
    - Product facts and prices ALWAYS come from Channel3 / ProductService.
    - Never invents products/attributes, never authorizes payment, and never turns follow-ups into unrelated searches.
    """

    def __init__(self, fallback: MockAIService):
        self.fallback = fallback
        self.gemini_key = settings.GEMINI_API_KEY
        self.openai_key = settings.OPENAI_API_KEY

    def _requested_provider(self) -> str:
        return (settings.AI_PROVIDER or "auto").strip().lower()

    def is_configured(self) -> bool:
        mode = self._requested_provider()
        if mode == "mock":
            return False
        if mode == "gemini":
            return bool(self.gemini_key and self.gemini_key.strip())
        if mode == "openai":
            return bool(self.openai_key and self.openai_key.strip())
        return bool(self.gemini_key and self.gemini_key.strip()) or bool(self.openai_key and self.openai_key.strip())

    def get_provider_name(self) -> str:
        mode = self._requested_provider()
        if mode == "mock":
            return "Deterministic Mock (Configured)"
        if mode == "gemini":
            if self.gemini_key and self.gemini_key.strip():
                return "Google Gemini (gemini-3-flash-preview)"
            return "Google Gemini (API key missing)"
        if mode == "openai":
            if self.openai_key and self.openai_key.strip():
                return "OpenAI (gpt-4o-mini)"
            return "OpenAI (API key missing)"
        if self.gemini_key and self.gemini_key.strip():
            return "Google Gemini (gemini-3-flash-preview)"
        if self.openai_key and self.openai_key.strip():
            return "OpenAI (gpt-4o-mini)"
        return "Deterministic Mock (Fallback)"

    async def process_user_intent(
        self,
        user_text: str,
        input_mode: str = "text",
        active_search_id: Optional[str] = None,
        search_generation: Optional[int] = None,
        visible_product_ids: Optional[List[str]] = None,
        raw_transcript: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        turn_ctx = self.fallback._prepare_turn_context(
            user_text,
            input_mode=input_mode,
            active_search_id=active_search_id,
            search_generation=search_generation,
            visible_product_ids=visible_product_ids,
            raw_transcript=raw_transcript,
            context_data=context_data,
        )
        normalized_text = turn_ctx["normalized_text"]
        if not normalized_text:
            return self.fallback._empty_transcript_response(turn_ctx)

        async def delegate_to_fallback() -> Dict[str, Any]:
            self.fallback.conversation_history.append({"role": "user", "text": normalized_text})
            action_fallback = classify_user_action(
                normalized_text,
                self.fallback.session,
                context=turn_ctx.get("context_data"),
            )
            return await self.fallback.execute_classified_action(
                normalized_text,
                action_fallback,
                provider_label="mock",
                turn_ctx=turn_ctx,
            )

        mode = self._requested_provider()
        if mode == "gemini" and not (self.gemini_key and self.gemini_key.strip()):
            logger.error("AI_PROVIDER=gemini but GEMINI_API_KEY is missing in backend/.env.")
            return await delegate_to_fallback()
        if mode == "openai" and not (self.openai_key and self.openai_key.strip()):
            logger.error("AI_PROVIDER=openai but OPENAI_API_KEY is missing in backend/.env.")
            return await delegate_to_fallback()

        if not self.is_configured():
            return await delegate_to_fallback()

        session = self.fallback.session
        det_action = classify_user_action(
            normalized_text,
            session,
            context=turn_ctx.get("context_data"),
        )

        # Safety-critical & purely cached conversational session actions always execute deterministically
        deterministic_actions = {
            ConversationalAction.CONFIRMATION_ATTEMPT,
            ConversationalAction.CANCEL,
            ConversationalAction.GO_BACK,
            ConversationalAction.HELP,
            ConversationalAction.OPEN_SHOP,
            ConversationalAction.OPEN_CART,
            ConversationalAction.CLEAR_CART,
            ConversationalAction.VIEW_CART,
            ConversationalAction.CHECK_TOTAL,
            ConversationalAction.PREPARE_CHECKOUT,
            ConversationalAction.READ_REVIEW,
            ConversationalAction.PROCEED_TO_CONFIRMATION,
            ConversationalAction.PAYPAL_APPROVAL_NAVIGATION,
            ConversationalAction.READ_RECEIPT,
            ConversationalAction.READ_ORDER_ID,
            ConversationalAction.RETRY_PAYMENT,
            ConversationalAction.ADD_TO_CART,
            ConversationalAction.REMOVE_FROM_CART,
            ConversationalAction.CHANGE_QUANTITY,
            ConversationalAction.COMPARE,
            ConversationalAction.SELECT,
            ConversationalAction.PRODUCT_DETAILS,
            ConversationalAction.SORT_RESULTS,
            ConversationalAction.SHOW_MORE,
            ConversationalAction.NEXT_OPTION,
            ConversationalAction.PREVIOUS_OPTION,
            ConversationalAction.CHEAPER_ALTERNATIVE,
            ConversationalAction.OTHER_ALTERNATIVE,
            ConversationalAction.FILTER_RESULTS,
            ConversationalAction.REFINE_SEARCH,
            ConversationalAction.SAVE_ITEM,
            ConversationalAction.VIEW_SAVED_ITEMS,
            ConversationalAction.OPEN_SAVED_ITEM,
            ConversationalAction.ADD_SAVED_ITEM_TO_CART,
            ConversationalAction.REMOVE_SAVED_ITEM,
            ConversationalAction.SAVE_SEARCH,
            ConversationalAction.VIEW_SAVED_SEARCHES,
            ConversationalAction.OPEN_SAVED_SEARCH,
            ConversationalAction.VIEW_ORDERS,
            ConversationalAction.OPEN_ORDER,
            ConversationalAction.OPEN_PREVIOUS_ORDER,
            ConversationalAction.ORDER_DETAIL_QUERY,
            ConversationalAction.REORDER,
        }
        if det_action.action in deterministic_actions:
            self.fallback.conversation_history.append({"role": "user", "text": normalized_text})
            return await self.fallback.execute_classified_action(
                normalized_text,
                det_action,
                provider_label="mock",
                turn_ctx=turn_ctx,
            )

        user_text = normalized_text

        recent_history = self.fallback.conversation_history[-6:]
        current_results_summary = [
            {
                "index": idx,
                "id": p.get("id"),
                "title": p.get("title"),
                "price": p.get("price"),
                "merchant": p.get("merchant"),
                "features": p.get("documented_accessibility_features", []),
            }
            for idx, p in enumerate(session.displayed_products)
        ]

        system_prompt = f"""You are AccessPay AI, an accessible shopping assistant.
CORE MOTTO: AI does the navigating. You make the decisions.

STRICT RULES:
1. Never invent products, prices, merchants, URLs, or missing product features.
2. Never authorize payment or override confirmation.
3. Preserve full meaningful keywords (brand, character/franchise, model, product type, color, compatibility, use-case) in `search_query`.
4. Distinguish `NEW_SEARCH` (`starts_new_search: true`) from follow-up `REFINE_SEARCH`, `FILTER_RESULTS`, `SHOW_MORE`, `COMPARE`, `SELECT`, `PRODUCT_DETAILS`, `CHEAPER_ALTERNATIVE`, `OTHER_ALTERNATIVE`, `SAVE_ITEM`, `VIEW_SAVED_ITEMS`, `REMOVE_SAVED_ITEM`, `SAVE_SEARCH`, `VIEW_SAVED_SEARCHES`, `OPEN_SAVED_SEARCH`, `VIEW_ORDERS`, `REORDER`, or `UNKNOWN`.
5. Never turn unknown conversational phrases or follow-up questions about displayed products (attributes, price, shipping, compatibility, warranty, stock, differences) into a new product search.
6. Return valid JSON ONLY matching:
{{
  "action": "NEW_SEARCH" | "REFINE_SEARCH" | "FILTER_RESULTS" | "SORT_RESULTS" | "SHOW_MORE" | "COMPARE" | "SELECT" | "PRODUCT_DETAILS" | "CHEAPER_ALTERNATIVE" | "OTHER_ALTERNATIVE" | "SAVE_ITEM" | "VIEW_SAVED_ITEMS" | "REMOVE_SAVED_ITEM" | "SAVE_SEARCH" | "VIEW_SAVED_SEARCHES" | "OPEN_SAVED_SEARCH" | "VIEW_ORDERS" | "REORDER" | "CLARIFICATION_NEEDED" | "HELP" | "UNKNOWN",
  "references": [],
  "constraint_updates": {{}},
  "starts_new_search": false,
  "needs_clarification": false,
  "clarification_question": null,
  "search_query": "concise search query preserving brand/model/product/color (without price words) or null",
  "product_type": "core product noun or null",
  "brand": null,
  "character_or_franchise": null,
  "model": null,
  "color": null,
  "size": null,
  "compatibility": null,
  "recipient_or_use_case": null,
  "max_price": null,
  "min_price": null,
  "features": []
}}

ACTIVE SESSION GENERATION: {session.search_generation}
ACTIVE PRODUCT QUERY: {json.dumps(session.structured_search_intent.model_dump() if session.structured_search_intent else None)}
DISPLAYED PRODUCTS: {json.dumps(current_results_summary)}
RECENT CONVERSATION: {json.dumps(recent_history)}
"""

        req_gen_before = session.search_generation
        try:
            use_gemini = mode in ("gemini", "auto") and bool(self.gemini_key and self.gemini_key.strip())
            use_openai = (not use_gemini) and mode in ("openai", "auto") and bool(self.openai_key and self.openai_key.strip())

            parsed: Optional[Dict[str, Any]] = None
            provider_label = "llm"

            if use_gemini:
                url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent"
                headers = {"Content-Type": "application/json", "x-goog-api-key": self.gemini_key.strip()}
                payload = {
                    "contents": [{"role": "user", "parts": [{"text": system_prompt + f"\nUser request: {user_text}"}]}],
                    "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
                }
                async with httpx.AsyncClient(timeout=12.0) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        text_resp = data["candidates"][0]["content"]["parts"][0]["text"]
                        parsed = json.loads(text_resp)
                        provider_label = "gemini-3-flash-preview"
                    elif resp.status_code in (400, 401, 403):
                        logger.error("Gemini authentication/request failed (HTTP %s). Verify GEMINI_API_KEY in backend/.env.", resp.status_code)
                    else:
                        logger.error("Gemini API failed with HTTP %s.", resp.status_code)

            elif use_openai:
                url = "https://api.openai.com/v1/chat/completions"
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_text}],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                }
                headers = {"Authorization": f"Bearer {self.openai_key.strip()}"}
                async with httpx.AsyncClient(timeout=6.0) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        text_resp = data["choices"][0]["message"]["content"]
                        parsed = json.loads(text_resp)
                        provider_label = "gpt-4o-mini"
                    elif resp.status_code in (401, 403):
                        logger.error("OpenAI authentication failed (HTTP %s). Verify OPENAI_API_KEY in backend/.env.", resp.status_code)
                    else:
                        logger.error("OpenAI API failed with HTTP %s.", resp.status_code)

            if req_gen_before != session.search_generation:
                return {"action": "STALE_DISCARDED", "stale": True, "search_generation": session.search_generation}

            if parsed is not None:
                validated = self._validate_llm_action(parsed, user_text, det_action)
                self.fallback.conversation_history.append({"role": "user", "text": user_text.strip()})
                return await self.fallback.execute_classified_action(
                    user_text,
                    validated,
                    provider_label=provider_label,
                    turn_ctx=turn_ctx,
                )

        except Exception as exc:
            logger.warning("Live LLM call failed (%s); falling back to deterministic engine.", type(exc).__name__)

        return await delegate_to_fallback()

    def _validate_llm_action(
        self,
        llm_output: Dict[str, Any],
        user_text: str,
        det_action: StructuredActionOutput,
    ) -> StructuredActionOutput:
        """
        Server-side validator ensuring Gemini output conforms to ConversationalAction,
        cannot authorize payment, and cannot misclassify conversational follow-ups or
        unknown phrases as new Channel3 searches.
        """
        raw_action = str(llm_output.get("action") or "").upper().strip()
        if raw_action == "SEARCH_RESULTS":
            raw_action = "NEW_SEARCH" if llm_output.get("starts_new_search", True) else "REFINE_SEARCH"

        try:
            chosen_action = ConversationalAction(raw_action)
        except ValueError:
            chosen_action = det_action.action

        # Guard: if deterministic classifier identified a conversational follow-up, command,
        # help/greeting, or UNKNOWN fragment, NEVER allow the LLM to hallucinate a NEW_SEARCH.
        if chosen_action == ConversationalAction.NEW_SEARCH and det_action.action != ConversationalAction.NEW_SEARCH:
            return det_action

        # Guard: if an active search already has displayed results and the user asks a short question
        # ending with '?' without an explicit new search request, answer on active context rather than NEW_SEARCH.
        sess_displayed = getattr(self.fallback.session, "displayed_products", [])
        if chosen_action == ConversationalAction.NEW_SEARCH and sess_displayed and user_text.strip().endswith("?"):
            lowered = user_text.lower()
            if not any(kw in lowered for kw in ("search for", "look for", "find me", "shop for", "new search")):
                return StructuredActionOutput(action=ConversationalAction.PRODUCT_DETAILS, references=["0"])

        # Guard: if LLM tried CONFIRMATION_ATTEMPT, require deterministic ConfirmationService handling
        if chosen_action == ConversationalAction.CONFIRMATION_ATTEMPT:
            return StructuredActionOutput(action=ConversationalAction.CONFIRMATION_ATTEMPT)

        def _float_or_none(v: Any) -> Optional[float]:
            if v is None:
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        return StructuredActionOutput(
            action=chosen_action,
            references=[str(r) for r in (llm_output.get("references") or []) if r is not None],
            constraint_updates=dict(llm_output.get("constraint_updates") or {}),
            starts_new_search=(chosen_action == ConversationalAction.NEW_SEARCH),
            needs_clarification=bool(llm_output.get("needs_clarification")),
            clarification_question=llm_output.get("clarification_question"),
            search_query=(str(llm_output.get("search_query")).strip() if llm_output.get("search_query") else det_action.search_query),
            product_type=(str(llm_output.get("product_type")).strip() if llm_output.get("product_type") else det_action.product_type),
            brand=(str(llm_output.get("brand")).strip() if llm_output.get("brand") else det_action.brand),
            model=(str(llm_output.get("model")).strip() if llm_output.get("model") else det_action.model),
            character_or_franchise=(str(llm_output.get("character_or_franchise")).strip() if llm_output.get("character_or_franchise") else det_action.character_or_franchise),
            max_price=_float_or_none(llm_output.get("max_price")) if llm_output.get("max_price") is not None else det_action.max_price,
            min_price=_float_or_none(llm_output.get("min_price")) if llm_output.get("min_price") is not None else det_action.min_price,
            color=(str(llm_output.get("color")).strip().lower() if llm_output.get("color") else det_action.color),
            size=(str(llm_output.get("size")).strip() if llm_output.get("size") else det_action.size),
            features=[str(f).strip().lower() for f in (llm_output.get("features") or llm_output.get("requirements") or []) if str(f).strip()],
            compatibility=(str(llm_output.get("compatibility")).strip() if llm_output.get("compatibility") else det_action.compatibility),
            recipient_or_use_case=(str(llm_output.get("recipient_or_use_case")).strip() if llm_output.get("recipient_or_use_case") else det_action.recipient_or_use_case),
            sort_preference=llm_output.get("sort_preference") or det_action.sort_preference,
        )


class AIService:
    """
    Unified AI Service Facade:
    Exposes a unified interface for FastAPI routes, delegating to LLMAIService
    with automatic fallback to MockAIService, backed by one ShoppingSession.
    """

    def __init__(self):
        self.mock_service = MockAIService()
        self.llm_service = LLMAIService(fallback=self.mock_service)

    def reset_conversation(self):
        self.mock_service.reset_conversation()

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_llm_configured": self.llm_service.is_configured(),
            "active_provider": self.llm_service.get_provider_name(),
            "product_mode": product_service.get_mode_status(),
            "fallback_available": True,
            "session_turns": len(self.mock_service.conversation_history),
            "session_id": self.mock_service.session.session_id,
            "search_generation": self.mock_service.session.search_generation,
        }

    async def process_user_intent(
        self,
        user_text: str,
        input_mode: str = "text",
        active_search_id: Optional[str] = None,
        search_generation: Optional[int] = None,
        visible_product_ids: Optional[List[str]] = None,
        raw_transcript: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            return await self.llm_service.process_user_intent(
                user_text,
                input_mode=input_mode,
                active_search_id=active_search_id,
                search_generation=search_generation,
                visible_product_ids=visible_product_ids,
                raw_transcript=raw_transcript,
                context_data=context_data,
            )
        except Exception as exc:
            logger.exception("Unhandled error in AIService.process_user_intent: %s", exc)
            safe_msg = "I'm having trouble searching right now.\nPlease try again."
            return {
                "action": "SEARCH_ERROR",
                "error": True,
                "count": 0,
                "products": [],
                "message": safe_msg,
                "speech_response": "I'm having trouble searching right now. Please try again.",
                "provider": "fallback",
                "search_id": self.mock_service.session.search_id,
                "search_generation": self.mock_service.session.search_generation,
            }


ai_service = AIService()
mock_ai_service = ai_service.mock_service
