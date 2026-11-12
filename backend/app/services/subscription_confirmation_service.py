import re
import uuid
from typing import Optional
from app.db.database import db
from app.models.subscription import (
    SubscriptionOffer,
    SubscriptionReview,
    SubscriptionConfirmResponse,
)

CASUAL_SUBSCRIPTION_PHRASES = {
    "yes",
    "yeah",
    "yep",
    "okay",
    "ok",
    "sure",
    "go ahead",
    "subscribe",
    "buy it",
    "continue",
    "sounds good",
    "click confirm",
    "confirm",
    "do it",
    "looks good",
}


class SubscriptionConfirmationService:
    """
    Separate deterministic recurring-commitment safety gate for subscriptions.
    Requires BOTH exact recurring amount AND exact billing frequency in the spoken phrase.
    """

    def __init__(self):
        self._active_review: Optional[SubscriptionReview] = None
        self._confirmation_granted: bool = False
        self._confirmed_phrase: Optional[str] = None
        self._confirmed_method: str = "VOICE"

    @staticmethod
    def build_expected_phrase(offer: SubscriptionOffer) -> str:
        return f"Confirm ${offer.recurring_amount:.2f} {offer.billing_frequency} subscription"

    def prepare_review(self, offer: SubscriptionOffer) -> SubscriptionReview:
        # Changing or re-preparing a plan invalidates any previous confirmation (Phase 32)
        if self._active_review and self._active_review.offer.id != offer.id:
            db.log_audit_event(
                "SUBSCRIPTION_PLAN_CHANGED_INVALIDATED",
                f"Previous subscription confirmation for {self._active_review.offer.id} invalidated on switch to {offer.id}",
                "SYSTEM",
            )
        self._confirmation_granted = False
        self._confirmed_phrase = None

        expected = self.build_expected_phrase(offer)
        review = SubscriptionReview(
            review_token=f"subrev_{uuid.uuid4().hex[:10]}",
            offer=offer,
            due_today=round(float(offer.amount_due_today), 2),
            recurring_amount=round(float(offer.recurring_amount), 2),
            billing_frequency=offer.billing_frequency,
            expected_phrase=expected,
            is_invalidated=False,
            confirmation_granted=False,
        )
        self._active_review = review
        db.log_audit_event(
            "SUBSCRIPTION_REVIEW_PREPARED",
            f"Prepared recurring review for {offer.id} (${offer.recurring_amount:.2f} {offer.billing_frequency})",
            "SYSTEM",
        )
        return review

    def get_active_review(self) -> Optional[SubscriptionReview]:
        return self._active_review

    def is_confirmation_granted(self, review_token: Optional[str] = None) -> bool:
        if not self._active_review or self._active_review.is_invalidated or not self._confirmation_granted:
            return False
        if review_token and self._active_review.review_token != review_token:
            return False
        return True

    def invalidate_current(self, reason: str) -> None:
        if self._active_review:
            self._active_review.is_invalidated = True
            self._active_review.invalidation_reason = reason
            self._active_review.confirmation_granted = False
        self._confirmation_granted = False
        self._confirmed_phrase = None

    def confirm_subscription(
        self,
        review_token: str,
        spoken_phrase: str,
        method: str = "VOICE",
    ) -> SubscriptionConfirmResponse:
        if not self._active_review or self._active_review.review_token != review_token:
            return SubscriptionConfirmResponse(
                success=False,
                is_ambiguous=True,
                message="Your subscription review expired or changed. Please review the plan again.",
                review_token=review_token,
                expected_phrase=self._active_review.expected_phrase if self._active_review else "",
            )

        if self._active_review.is_invalidated:
            return SubscriptionConfirmResponse(
                success=False,
                is_ambiguous=True,
                message="Your subscription plan changed. Please review the updated terms before confirming.",
                review_token=review_token,
                expected_phrase=self._active_review.expected_phrase,
            )

        expected = self._active_review.expected_phrase
        clean = re.sub(r"\s+", " ", (spoken_phrase or "").strip().lower()).rstrip(".!?,")

        # 1. Reject casual/ambiguous consent phrases
        if clean in CASUAL_SUBSCRIPTION_PHRASES or not clean:
            db.log_audit_event("SUBSCRIPTION_CASUAL_CONSENT_REJECTED", f"Rejected '{spoken_phrase}'", method)
            return SubscriptionConfirmResponse(
                success=False,
                is_ambiguous=True,
                message=f'Casual consent does not authorize a recurring subscription. Say "{expected}".',
                review_token=review_token,
                expected_phrase=expected,
            )

        has_confirm = "confirm" in clean
        has_sub_word = "subscription" in clean or "recurring" in clean
        expected_amt_str = f"{self._active_review.recurring_amount:.2f}"
        expected_freq = self._active_review.billing_frequency.lower()

        # Check dollar amount in spoken phrase
        amounts = re.findall(r"\$?\s*(\d+(?:\.\d{1,2})?)", clean)
        matched_amount = False
        wrong_amount = False
        if amounts:
            for amt_raw in amounts:
                try:
                    if abs(float(amt_raw) - self._active_review.recurring_amount) < 0.005:
                        matched_amount = True
                        break
                except ValueError:
                    continue
            if not matched_amount:
                wrong_amount = True

        # Check billing frequency in spoken phrase
        freq_synonyms = {
            "monthly": {"monthly", "month"},
            "yearly": {"yearly", "annual", "annually", "year"},
            "weekly": {"weekly", "week"},
        }
        expected_words = freq_synonyms.get(expected_freq, {expected_freq})
        other_words = {
            w
            for freq_key, words in freq_synonyms.items()
            if freq_key != expected_freq
            for w in words
        }
        matched_frequency = any(re.search(rf"\b{re.escape(w)}\b", clean) for w in expected_words)
        wrong_frequency = any(re.search(rf"\b{re.escape(w)}\b", clean) for w in other_words) and not matched_frequency

        if wrong_amount:
            db.log_audit_event(
                "SUBSCRIPTION_WRONG_AMOUNT_REJECTED",
                f"Rejected '{spoken_phrase}', expected ${expected_amt_str}",
                method,
            )
            return SubscriptionConfirmResponse(
                success=False,
                wrong_amount=True,
                message=f'That amount does not match ${expected_amt_str}. Say "{expected}".',
                review_token=review_token,
                expected_phrase=expected,
            )

        if wrong_frequency or not matched_frequency:
            db.log_audit_event(
                "SUBSCRIPTION_WRONG_FREQUENCY_REJECTED",
                f"Rejected '{spoken_phrase}', expected {expected_freq}",
                method,
            )
            return SubscriptionConfirmResponse(
                success=False,
                wrong_frequency=True,
                message=f'Billing frequency must be {expected_freq}. Say "{expected}".',
                review_token=review_token,
                expected_phrase=expected,
            )

        if not (has_confirm and has_sub_word and matched_amount and matched_frequency):
            db.log_audit_event("SUBSCRIPTION_PHRASE_REJECTED", f"Rejected '{spoken_phrase}'", method)
            return SubscriptionConfirmResponse(
                success=False,
                is_ambiguous=True,
                message=f'Please say the exact recurring confirmation phrase: "{expected}".',
                review_token=review_token,
                expected_phrase=expected,
            )

        self._confirmation_granted = True
        self._confirmed_phrase = spoken_phrase
        self._confirmed_method = method
        self._active_review.confirmation_granted = True
        db.log_audit_event(
            "SUBSCRIPTION_CONFIRMED",
            f"Explicit recurring commitment authorized for {self._active_review.offer.id}: {expected}",
            method,
        )
        return SubscriptionConfirmResponse(
            success=True,
            message="Recurring subscription commitment confirmed. Opening PayPal Sandbox subscription approval.",
            review_token=review_token,
            expected_phrase=expected,
        )

    @staticmethod
    def build_cancellation_phrase(plan_name: str) -> str:
        return f"Confirm cancellation of {plan_name}"

    @staticmethod
    def verify_cancellation_phrase(plan_name: str, spoken_phrase: str) -> bool:
        clean = re.sub(r"\s+", " ", (spoken_phrase or "").strip().lower()).rstrip(".!?,")
        if clean in CASUAL_SUBSCRIPTION_PHRASES:
            return False
        norm_plan = re.sub(r"\s+", " ", plan_name.strip().lower())
        short_plan = norm_plan.split("—")[0].strip()
        return (
            "confirm" in clean
            and "cancel" in clean
            and (norm_plan in clean or (len(short_plan) >= 4 and short_plan in clean))
        )


subscription_confirmation_service = SubscriptionConfirmationService()

