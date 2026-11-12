from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from app.config import settings
from app.models.purchase import PurchaseState
from app.services.payment_service import payment_service, SAFE_PAYMENT_FAILURE_MESSAGE
from app.services.cart_service import cart_service
from app.services.confirmation_service import confirmation_service
from app.services.order_service import order_service
from app.services.accessibility_service import accessibility_service

router = APIRouter(prefix="/payments", tags=["Payments"])


class CreatePayPalOrderRequest(BaseModel):
    review_token: Optional[str] = None
    return_url: Optional[str] = None
    cancel_url: Optional[str] = None


class CapturePayPalOrderRequest(BaseModel):
    review_token: Optional[str] = None
    interaction_mode: Optional[str] = None
    confirmation_method: Optional[str] = None


class CreatePaymentRequest(BaseModel):
    amount: float
    currency: str = "USD"
    description: Optional[str] = "AccessPay AI Order"


class CapturePaymentRequest(BaseModel):
    paypal_order_id: str


class SimulateFailureRequest(BaseModel):
    simulate: bool


class SetPaymentProviderRequest(BaseModel):
    provider: str  # 'paypal', 'mock', or 'auto'


@router.get("/config")
def get_public_paypal_config():
    """
    Returns public-only PayPal Sandbox configuration for the frontend SDK.
    NEVER exposes PAYPAL_CLIENT_SECRET.
    """
    return {
        "paypal_client_id": settings.PAYPAL_CLIENT_ID if payment_service.is_paypal_configured() else "",
        "environment": "sandbox",
        "provider": payment_service.get_active_provider(),
        "is_configured": payment_service.is_paypal_configured(),
        "sandbox_label": "Demo payment — PayPal Sandbox",
        "agent_ready_note": "Agent Ready integration path identified; current prototype uses PayPal Sandbox Checkout/Orders API.",
    }


@router.post(
    "/paypal/create-order",
    summary="Create PayPal Sandbox order after explicit confirmation",
    description=(
        "Creates a one-time PayPal Sandbox order (Orders API v2) using server-authoritative totals. "
        "Requires prior explicit exact-amount confirmation and PayPal buyer approval before capture."
    ),
)
async def create_paypal_sandbox_order(req: Optional[CreatePayPalOrderRequest] = None):
    """
    Server-controlled PayPal Sandbox Order creation:
    1. Load current cart (server is source of truth — never trusts browser price).
    2. Verify selected product & active review confirmation.
    3. Revalidate price, shipping, tax, quantity, variant, and recurring terms.
    4. Calculate item total, shipping/tax, and final total.
    5. Create PayPal Sandbox order with idempotency protection.
    6. Return only required order information to frontend.
    """
    review = confirmation_service.get_active_review()
    if not review:
        return {
            "success": False,
            "state": confirmation_service.get_state(),
            "message": "Please review and confirm your purchase before starting PayPal checkout.",
        }

    if req and req.review_token and req.review_token != review.review_token:
        return {
            "success": False,
            "state": PurchaseState.PAYMENT_REVIEW,
            "message": "Your payment review expired. Please review the updated total.",
        }

    # Price-Change & Total-Change Protection before creating PayPal order
    valid_integrity, integrity_err = confirmation_service.verify_price_integrity()
    if not valid_integrity:
        return {
            "success": False,
            "price_changed": True,
            "state": PurchaseState.PAYMENT_REVIEW,
            "message": integrity_err or "The price changed.\n\nPlease review the updated total.",
        }

    # Verify explicit AccessPay confirmation was granted
    if not confirmation_service.is_confirmation_granted():
        return {
            "success": False,
            "state": PurchaseState.CONFIRMATION_REQUIRED,
            "message": f"Explicit confirmation is required before PayPal checkout. Say '{review.expected_phrase}' or activate Confirm.",
        }

    # Load server-side cart and recalculate totals
    cart = cart_service.get_cart()
    if not cart.items:
        return {
            "success": False,
            "state": PurchaseState.BROWSING,
            "message": "Your cart is empty. No payment was made.",
        }

    if cart.has_subscriptions and not review.subscription_acknowledged:
        return {
            "success": False,
            "state": PurchaseState.CONFIRMATION_REQUIRED,
            "message": "Recurring payment acknowledgement is required before proceeding to PayPal.",
        }

    item_total = cart.subtotal
    shipping_total = cart.shipping_total
    tax_total = cart.tax_total
    discount_total = cart.discount_total
    final_total = cart.total_today

    meta = order_service.summarize_cart_metadata(cart)
    line_items = order_service.build_order_line_items(cart)
    description = f"{meta['product_title']} ({meta['merchant']})"
    order_res = await payment_service.create_order(
        amount=final_total,
        currency="USD",
        description=description,
        cart=cart,
        idempotency_key=review.review_token,
        return_url=req.return_url if req else None,
        cancel_url=req.cancel_url if req else None,
    )

    if not order_res.get("success"):
        if order_res.get("duplicate"):
            return {
                "success": False,
                "duplicate": True,
                "state": PurchaseState.PAYMENT_PROCESSING,
                "message": "Processing payment...",
            }
        fail_resp = confirmation_service.fail_payment(order_res.get("error", "Order creation failed"))
        return {
            "success": False,
            "state": fail_resp.state,
            "message": SAFE_PAYMENT_FAILURE_MESSAGE,
        }

    paypal_order_id = order_res.get("paypal_order_id")
    confirmation_service.set_active_paypal_order_id(paypal_order_id)

    return {
        "success": True,
        "paypal_order_id": paypal_order_id,
        "status": order_res.get("status", "CREATED"),
        "amount": final_total,
        "item_subtotal": item_total,
        "shipping": shipping_total,
        "tax": tax_total,
        "discount": discount_total,
        "currency": "USD",
        "product_title": meta["product_title"],
        "merchant": meta["merchant"],
        "item_count": cart.item_count,
        "items": [li.model_dump() for li in line_items],
        "is_subscription": cart.has_subscriptions,
        "subscription_terms": cart.future_payments if cart.has_subscriptions else None,
        "subscription_note": (
            "Recurring payment demo safety scenario — PayPal Orders API processes a single Sandbox authorization."
            if cart.has_subscriptions
            else None
        ),
        "provider": order_res.get("provider", payment_service.get_active_provider()),
        "environment": "sandbox",
        "approval_url": order_res.get("approval_url"),
    }


@router.get("/paypal/order/{order_id}", summary="Get PayPal Sandbox order status")
async def get_paypal_order_status(order_id: str):
    """
    Safely inspects live PayPal Sandbox order status (CREATED, APPROVED, COMPLETED)
    so the UI only attempts capture after PayPal buyer approval.
    """
    return await payment_service.get_order_status(order_id)


@router.post(
    "/paypal/capture-order/{order_id}",
    summary="Capture approved PayPal Sandbox order",
    description="Captures an approved PayPal Sandbox order and records the completed order with its PayPal capture ID.",
)
async def capture_paypal_sandbox_order(order_id: str, req: Optional[CapturePayPalOrderRequest] = None):
    """
    Captures an approved PayPal Sandbox order:
    1. Verify the order and re-verify price/total integrity.
    2. Capture through PayPal Sandbox with duplicate-capture protection.
    3. Verify PayPal response.
    4. Record transaction & update purchase history in SQLite.
    5. Return accessible success/failure result.
    """
    if not order_id or not order_id.strip():
        return {
            "success": False,
            "state": PurchaseState.PAYMENT_FAILED,
            "message": SAFE_PAYMENT_FAILURE_MESSAGE,
        }

    review = confirmation_service.get_active_review()
    if review:
        valid_integrity, integrity_err = confirmation_service.verify_price_integrity()
        if not valid_integrity:
            return {
                "success": False,
                "price_changed": True,
                "state": PurchaseState.PAYMENT_REVIEW,
                "message": integrity_err or "The price changed.\n\nPlease review the updated total.",
            }

    cart = cart_service.get_cart()
    if not cart.items:
        return {
            "success": False,
            "state": PurchaseState.PAYMENT_FAILED,
            "message": SAFE_PAYMENT_FAILURE_MESSAGE,
        }

    total_charged = cart.total_today
    is_sub = cart.has_subscriptions or cart.has_trials

    capture_res = await payment_service.capture_order(
        paypal_order_id=order_id,
        idempotency_key=f"capture-{order_id}",
    )

    if not capture_res.get("success"):
        if capture_res.get("duplicate"):
            return {
                "success": False,
                "duplicate": True,
                "state": PurchaseState.PAYMENT_PROCESSING,
                "message": "Processing payment...",
            }
        fail_resp = confirmation_service.fail_payment(capture_res.get("error", "PayPal capture failed"))
        return {
            "success": False,
            "state": fail_resp.state,
            "message": SAFE_PAYMENT_FAILURE_MESSAGE,
        }

    confirmed_details = confirmation_service.get_confirmed_details()
    prefs = accessibility_service.get_preferences()
    interaction_mode = (req.interaction_mode if req and req.interaction_mode else None) or prefs.current_mode
    method_label = (
        (req.confirmation_method if req and req.confirmation_method else None)
        or confirmed_details.get("method")
        or interaction_mode
    )
    phrase_used = confirmed_details.get("phrase") or f"CONFIRM ${total_charged:.2f}"
    capture_id = capture_res.get("paypal_capture_id")

    # Record transaction and update purchase history
    order = order_service.create_order_from_cart(
        paypal_order_id=order_id,
        confirmation_method=f"{method_label}: '{phrase_used}'",
        paypal_capture_id=capture_id,
        interaction_mode=interaction_mode,
    )

    complete_resp = confirmation_service.complete_payment(
        order_id=order.order_id,
        paypal_order_id=order_id,
        paypal_capture_id=capture_id,
        product_title=order.product_title,
        merchant=order.merchant,
        amount_charged=order.total,
        is_subscription=is_sub,
        items=order.items,
        item_subtotal=order.item_subtotal if order.item_subtotal is not None else order.item_price,
        shipping=order.shipping,
        tax=order.tax,
    )

    return {
        "success": True,
        "state": complete_resp.state,
        "message": "Payment successful",
        "order_id": order.order_id,
        "paypal_order_id": order_id,
        "paypal_capture_id": capture_id,
        "product_title": order.product_title,
        "merchant": order.merchant,
        "amount_charged": order.total,
        "item_subtotal": order.item_subtotal if order.item_subtotal is not None else order.item_price,
        "shipping": order.shipping,
        "tax": order.tax,
        "items": [li.model_dump() for li in order.items],
        "is_subscription": is_sub,
        "environment": "sandbox",
    }


@router.post("/create", summary="Create payment order", description="Create a payment order through the active sandbox payment service.")
async def create_payment_order(req: CreatePaymentRequest):
    return await payment_service.create_order(
        amount=req.amount,
        currency=req.currency,
        description=req.description or "AccessPay AI Order"
    )


@router.post("/capture", summary="Capture payment order", description="Capture an approved payment order through the active sandbox payment service.")
async def capture_payment(req: CapturePaymentRequest):
    return await payment_service.capture_order(req.paypal_order_id)


@router.post("/simulate-failure", summary="Toggle payment failure simulation", description="Enable or disable simulated payment gateway decline for testing failure handling.")
def toggle_payment_failure_simulation(req: SimulateFailureRequest):
    payment_service.set_simulate_failure(req.simulate)
    return {"status": "ok", "simulate_failure": req.simulate}


@router.post("/mode", summary="Set payment provider mode", description="Switch the active payment provider mode within the sandbox environment.")
def set_payment_provider_mode(req: SetPaymentProviderRequest):
    payment_service.set_provider(req.provider)
    return {
        "status": "ok",
        "provider": payment_service.get_active_provider(),
        "environment": "sandbox",
    }


@router.get("/status", summary="Get payment gateway status", description="Return configuration and sandbox readiness status for the PayPal Orders API v2 gateway.")
def get_payment_gateway_status():
    return {
        "gateway": "PayPal Sandbox Orders API v2",
        "is_configured": payment_service.is_paypal_configured(),
        "provider": payment_service.get_active_provider(),
        "mode": "sandbox",
        "environment": "sandbox"
    }
