from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.models.purchase import PurchaseReview, ConfirmPurchaseRequest, PurchaseResponse, PurchaseState
from app.services.confirmation_service import confirmation_service
from app.services.order_service import order_service
from app.services.payment_service import payment_service
from app.services.cart_service import cart_service

router = APIRouter(prefix="/purchase", tags=["Checkout"])


class PriceChangeSimulationRequest(BaseModel):
    new_price: float = 62.99


class SubscriptionAckRequest(BaseModel):
    acknowledged: bool = True


@router.post("/acknowledge-subscription", summary="Acknowledge subscription terms", description="Record explicit user acknowledgement of recurring subscription or trial terms on the active purchase review.")
def acknowledge_subscription(req: SubscriptionAckRequest):
    review = confirmation_service.get_active_review()
    if review:
        review.subscription_acknowledged = req.acknowledged
        review.trial_acknowledged = req.acknowledged
    return {"status": "ok", "subscription_acknowledged": req.acknowledged}


@router.get("/state", summary="Get current purchase confirmation state", description="Return the current confirmation state machine status and active purchase review, if any.")
def get_current_purchase_state():
    return {
        "state": confirmation_service.get_state(),
        "active_review": confirmation_service.get_active_review()
    }


@router.post(
    "/review",
    response_model=PurchaseReview,
    summary="Prepare server-authoritative purchase review",
    description="Computes server-authoritative item subtotal, shipping, tax, and total, and issues a review_token required before confirmation.",
)
def prepare_review():
    try:
        return confirmation_service.prepare_payment_review()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/confirm",
    response_model=PurchaseResponse,
    summary="Verify explicit exact-amount human confirmation",
    description=(
        "Enforces deterministic confirmation binding the exact server-computed total before PayPal order creation. "
        "Ambiguous consent ('yes', 'okay', 'go ahead') is rejected. AI may never silently authorize payment."
    ),
)
async def confirm_purchase(req: ConfirmPurchaseRequest):
    # Step 1: Deterministic validation of AccessPay confirmation conditions
    validation_resp = confirmation_service.validate_confirmation(
        token=req.review_token,
        spoken_phrase=req.spoken_phrase,
        confirmation_method=req.confirmation_method,
        subscription_ack=req.subscription_acknowledged,
        trial_ack=req.trial_acknowledged,
        high_value_step=req.high_value_step
    )

    if not validation_resp.success:
        return validation_resp

    # If authorize_only is True, AccessPay confirmation succeeded and the client
    # will now open PayPal Sandbox Checkout (POST /api/payments/paypal/create-order -> capture-order).
    if req.authorize_only:
        return validation_resp

    # Step 2: Execute server-controlled PayPal Sandbox order creation & capture
    cart = cart_service.get_cart()
    amount = cart.total_today if cart.items else (validation_resp.amount_charged or 0.0)
    meta = order_service.summarize_cart_metadata(cart) if cart.items else {}
    pay_order = await payment_service.create_order(
        amount=amount,
        description=f"{meta.get('product_title', 'AccessPay AI Order')} ({meta.get('merchant', 'Verified Merchant')})" if cart.items else "AccessPay AI Order",
        cart=cart if cart.items else None,
        idempotency_key=req.review_token
    )

    if not pay_order.get("success"):
        return confirmation_service.fail_payment(pay_order.get("error", "Payment failed"))

    paypal_id = pay_order.get("paypal_order_id", "PAYID-UNKNOWN")
    capture_res = await payment_service.capture_order(paypal_id)

    if not capture_res.get("success"):
        return confirmation_service.fail_payment(capture_res.get("error", "Capture failed"))

    capture_id = capture_res.get("paypal_capture_id")

    # Step 3: Record finalized order and complete purchase
    order = order_service.create_order_from_cart(
        paypal_order_id=paypal_id,
        confirmation_method=f"{req.confirmation_method}: '{req.spoken_phrase or 'Explicit Button'}'",
        paypal_capture_id=capture_id,
        interaction_mode=req.confirmation_method
    )

    return confirmation_service.complete_payment(
        order_id=order.order_id,
        paypal_order_id=paypal_id,
        paypal_capture_id=capture_id,
        product_title=order.product_title,
        merchant=order.merchant,
        amount_charged=order.total,
        is_subscription=order.is_recurring,
        items=order.items,
        item_subtotal=order.item_subtotal if order.item_subtotal is not None else order.item_price,
        shipping=order.shipping,
        tax=order.tax,
    )


@router.post("/cancel", response_model=PurchaseResponse, summary="Cancel active purchase review", description="Cancel the active purchase review and reset the confirmation gate without charging the user.")
def cancel_purchase():
    return confirmation_service.cancel_purchase("User commanded cancellation")


@router.post("/simulate-price-change", response_model=PurchaseReview, summary="Simulate a price change during checkout", description="Simulate a price change on the active review, invalidating any prior confirmation token.")
def simulate_price_change(req: PriceChangeSimulationRequest):
    return confirmation_service.simulate_price_change(req.new_price)
