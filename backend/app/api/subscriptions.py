from typing import List, Optional
from urllib.parse import urlparse
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db.database import db
from app.models.subscription import (
    PayPalSubscriptionCreateRequest,
    SubscriptionCancelRequest,
    SubscriptionConfirmRequest,
    SubscriptionConfirmResponse,
    SubscriptionOffer,
    SubscriptionRecord,
    SubscriptionReview,
    SubscriptionReviewRequest,
)
from app.services.paypal_subscription_service import paypal_subscription_service
from app.services.subscription_confirmation_service import subscription_confirmation_service
from app.services.subscription_provider import subscription_provider


def _is_valid_redirect_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme == "https" and bool(parsed.netloc):
            return True
        if parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1"):
            return True
        return False
    except Exception:
        return False

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


class SubscriptionQARequest(BaseModel):
    offer_id: str
    question: str


class SubscriptionQAResponse(BaseModel):
    offer_id: str
    answer: str


@router.get("/products", response_model=List[SubscriptionOffer], summary="List demo subscription plans")
async def list_subscription_products(q: Optional[str] = Query(default=None)):
    """Search the isolated Demo Subscription Catalog (never routed through Channel3)."""
    return subscription_provider.search(q)


@router.get("/records/list", response_model=List[SubscriptionRecord], summary="List user subscriptions")
async def list_user_subscriptions():
    """List persisted user subscriptions (separate from one-time Orders)."""
    return paypal_subscription_service.list_subscriptions()


@router.get("/{offer_id}", response_model=SubscriptionOffer, summary="Get demo subscription offer details", description="Retrieve full billing terms and metadata for a specific demo subscription offer.")
async def get_subscription_offer(offer_id: str):
    offer = subscription_provider.get_offer(offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="Subscription offer not found.")
    return offer


@router.post("/qa", response_model=SubscriptionQAResponse, summary="Answer questions about subscription terms", description="Answer user questions about renewal frequency, cancellation, and pricing for a subscription offer.")
async def answer_subscription_question(req: SubscriptionQARequest):
    offer = subscription_provider.get_offer(req.offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="Subscription offer not found.")
    answer = subscription_provider.answer_question(offer, req.question)
    return SubscriptionQAResponse(offer_id=offer.id, answer=answer)


@router.post(
    "/review",
    response_model=SubscriptionReview,
    summary="Prepare recurring subscription commitment review",
    description="Prepares recurring subscription disclosure (due today, recurring amount, billing frequency, renewal & cancellation terms) without creating any subscription.",
)
async def prepare_subscription_review(req: SubscriptionReviewRequest):
    offer = subscription_provider.get_offer(req.offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="Subscription offer not found.")
    return subscription_confirmation_service.prepare_review(offer)


@router.post(
    "/confirm",
    response_model=SubscriptionConfirmResponse,
    summary="Confirm recurring subscription amount and billing frequency",
    description="Deterministic confirmation gate requiring BOTH exact recurring amount and billing frequency. Distinct from one-time Orders confirmation.",
)
async def confirm_subscription_commitment(req: SubscriptionConfirmRequest):
    return subscription_confirmation_service.confirm_subscription(
        review_token=req.review_token,
        spoken_phrase=req.spoken_phrase,
        method=req.method,
    )


@router.post(
    "/paypal/create",
    response_model=SubscriptionRecord,
    summary="Create PayPal Sandbox subscription after recurring confirmation",
    description="Creates a PayPal Sandbox subscription via Subscriptions API v1 (/v1/billing/subscriptions). Blocked unless explicit recurring confirmation was granted.",
)
async def create_paypal_subscription(req: PayPalSubscriptionCreateRequest):
    if not subscription_confirmation_service.is_confirmation_granted(req.review_token):
        raise HTTPException(
            status_code=403,
            detail=(
                "Explicit recurring subscription confirmation is required before creating a "
                "PayPal Sandbox subscription. Please confirm both the exact recurring amount and billing frequency."
            ),
        )

    active_review = subscription_confirmation_service.get_active_review()
    if not active_review:
        raise HTTPException(status_code=400, detail="No active subscription review found.")

    if (req.return_url and not _is_valid_redirect_url(req.return_url)) or (
        req.cancel_url and not _is_valid_redirect_url(req.cancel_url)
    ):
        raise HTTPException(status_code=400, detail="Invalid redirect URL.")

    try:
        record = await paypal_subscription_service.create_subscription(
            offer=active_review.offer,
            return_url=req.return_url,
            cancel_url=req.cancel_url,
        )
        return record
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/paypal/status/{subscription_id}", response_model=SubscriptionRecord, summary="Get PayPal subscription status", description="Fetch the latest status of a PayPal Sandbox subscription by subscription ID.")
async def get_paypal_subscription_status(subscription_id: str):
    try:
        return await paypal_subscription_service.get_subscription_status(subscription_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/{subscription_id}/cancel", response_model=SubscriptionRecord, summary="Cancel PayPal subscription", description="Cancel an active PayPal Sandbox subscription after verifying the explicit cancellation confirmation phrase.")
async def cancel_paypal_subscription(subscription_id: str, req: SubscriptionCancelRequest):
    existing = db.get_subscription(subscription_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Subscription not found.")

    record = SubscriptionRecord(**existing)
    if not subscription_confirmation_service.verify_cancellation_phrase(
        record.plan_name, req.confirmation_phrase
    ):
        expected = subscription_confirmation_service.build_cancellation_phrase(record.plan_name)
        db.log_audit_event(
            "SUBSCRIPTION_CANCEL_REJECTED",
            f"Rejected ambiguous cancellation phrase for {subscription_id}",
            "USER",
        )
        raise HTTPException(
            status_code=400,
            detail=f'Please confirm cancellation explicitly by saying or typing: "{expected}."',
        )

    try:
        return await paypal_subscription_service.cancel_subscription(
            subscription_id=subscription_id,
            reason=req.reason or "User requested cancellation via AccessPay",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
