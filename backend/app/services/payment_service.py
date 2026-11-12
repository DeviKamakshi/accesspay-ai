from decimal import Decimal, ROUND_HALF_UP
import httpx
import base64
import uuid
import logging
from typing import Dict, Any, Optional, Set
from app.config import settings
from app.db.database import db
from app.models.cart import Cart

_CENT = Decimal("0.01")


def _dec_cents(value: float | int | str | Decimal) -> Decimal:
    return Decimal(str(value or 0)).quantize(_CENT, rounding=ROUND_HALF_UP)


def build_paypal_purchase_unit(
    amount: float,
    currency: str = "USD",
    description: str = "AccessPay AI Order",
    cart: Optional[Cart] = None,
) -> Dict[str, Any]:
    """Construct an authoritative PayPal v2 purchase_unit with exact cent breakdown across all cart items."""
    amount_dec = _dec_cents(amount)
    purchase_unit: Dict[str, Any] = {
        "description": (description or "AccessPay AI Order")[:127],
        "amount": {
            "currency_code": currency,
            "value": f"{amount_dec:.2f}",
        },
    }

    if cart and cart.items:
        paypal_items = []
        reconciled_item_total = Decimal("0.00")
        for item in cart.items:
            unit_dec = _dec_cents(item.product.price)
            reconciled_item_total += _dec_cents(unit_dec * item.quantity)
            paypal_items.append(
                {
                    "name": item.product.title[:127],
                    "quantity": str(item.quantity),
                    "unit_amount": {
                        "currency_code": currency,
                        "value": f"{unit_dec:.2f}",
                    },
                }
            )

        shipping_dec = _dec_cents(cart.shipping_total)
        tax_dec = _dec_cents(cart.tax_total)
        discount_dec = _dec_cents(cart.discount_total)
        subtotal_dec = _dec_cents(cart.subtotal)
        expected_total = _dec_cents(reconciled_item_total + shipping_dec + tax_dec - discount_dec)

        if reconciled_item_total == subtotal_dec and expected_total == amount_dec:
            breakdown: Dict[str, Dict[str, str]] = {
                "item_total": {"currency_code": currency, "value": f"{reconciled_item_total:.2f}"},
                "shipping": {"currency_code": currency, "value": f"{shipping_dec:.2f}"},
                "tax_total": {"currency_code": currency, "value": f"{tax_dec:.2f}"},
            }
            if discount_dec > Decimal("0.00"):
                breakdown["discount"] = {"currency_code": currency, "value": f"{discount_dec:.2f}"}
            purchase_unit["amount"]["breakdown"] = breakdown
            purchase_unit["items"] = paypal_items

    return purchase_unit

logger = logging.getLogger("accesspay.payment")

SAFE_PAYMENT_FAILURE_MESSAGE = "Your payment could not be completed.\n\nNothing was charged."
SANDBOX_BASE_URL = "https://api-m.sandbox.paypal.com"


class MockPaymentService:
    """
    Deterministic Mock Payment Service for offline/demo testing and fallback.
    Simulates PayPal Sandbox v2 Orders API responses without charging real money.
    """
    def __init__(self):
        self.orders: Dict[str, Dict[str, Any]] = {}

    async def create_order(
        self,
        amount: float,
        currency: str = "USD",
        description: str = "AccessPay AI Order",
        cart: Optional[Cart] = None,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        mock_id = f"PAYID-SBX-{uuid.uuid4().hex[:10].upper()}"
        order_record = {
            "id": mock_id,
            "status": "CREATED",
            "amount": round(amount, 2),
            "currency": currency,
            "description": description,
            "idempotency_key": idempotency_key,
        }
        self.orders[mock_id] = order_record
        db.log_audit_event(
            "MOCK_PAYMENT_ORDER_CREATED",
            f"ID: {mock_id}, Amount: ${amount:.2f}",
            "SYSTEM"
        )
        return {
            "success": True,
            "mode": "MOCK_PAYPAL_SANDBOX",
            "provider": "mock",
            "environment": "sandbox",
            "paypal_order_id": mock_id,
            "status": "CREATED",
            "amount": round(amount, 2),
            "currency": currency,
            "approval_url": f"https://www.sandbox.paypal.com/checkoutnow?token={mock_id}",
        }

    async def capture_order(
        self,
        paypal_order_id: str,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        capture_id = f"CAP-SBX-{uuid.uuid4().hex[:10].upper()}"
        if paypal_order_id in self.orders:
            self.orders[paypal_order_id]["status"] = "COMPLETED"
            self.orders[paypal_order_id]["capture_id"] = capture_id

        db.log_audit_event(
            "MOCK_PAYMENT_CAPTURED",
            f"Captured order {paypal_order_id} (Capture ID: {capture_id})",
            "SYSTEM"
        )
        return {
            "success": True,
            "mode": "MOCK_PAYPAL_SANDBOX",
            "provider": "mock",
            "environment": "sandbox",
            "paypal_order_id": paypal_order_id,
            "paypal_capture_id": capture_id,
            "status": "COMPLETED",
        }

    async def get_order_status(self, paypal_order_id: str) -> Dict[str, Any]:
        order = self.orders.get(paypal_order_id)
        if not order:
            return {
                "success": False,
                "paypal_order_id": paypal_order_id,
                "status": "UNKNOWN",
                "provider": "mock",
                "environment": "sandbox",
            }
        return {
            "success": True,
            "paypal_order_id": paypal_order_id,
            "status": order.get("status", "CREATED"),
            "paypal_capture_id": order.get("capture_id"),
            "amount": order.get("amount"),
            "currency": order.get("currency", "USD"),
            "provider": "mock",
            "environment": "sandbox",
        }


class PayPalPaymentService:
    """
    Official PayPal Sandbox Orders API v2 Service:
    - OAuth 2.0 token exchange: POST https://api-m.sandbox.paypal.com/v1/oauth2/token
    - Create Order: POST https://api-m.sandbox.paypal.com/v2/checkout/orders
    - Capture Order: POST https://api-m.sandbox.paypal.com/v2/checkout/orders/{id}/capture
    - Strictly enforces Sandbox URL (NEVER uses PayPal Live).
    """
    def __init__(self):
        self.client_id = settings.PAYPAL_CLIENT_ID
        self.client_secret = settings.PAYPAL_CLIENT_SECRET
        # Hard-enforce PayPal Sandbox URL; never permit live endpoint
        configured_url = settings.PAYPAL_BASE_URL or SANDBOX_BASE_URL
        if "sandbox.paypal.com" not in configured_url:
            logger.warning("Non-sandbox PayPal URL rejected; enforcing https://api-m.sandbox.paypal.com")
            configured_url = SANDBOX_BASE_URL
        self.base_url = configured_url

    def is_configured(self) -> bool:
        return bool(
            self.client_id
            and self.client_id.strip()
            and self.client_secret
            and self.client_secret.strip()
        )

    async def get_access_token(self) -> Optional[str]:
        if not (self.client_id and self.client_id.strip()):
            logger.error("PayPal Client ID missing. Set PAYPAL_CLIENT_ID in backend/.env.")
            return None
        if not (self.client_secret and self.client_secret.strip()):
            logger.error("PayPal Secret missing. Set PAYPAL_CLIENT_SECRET in backend/.env.")
            return None

        auth_str = f"{self.client_id.strip()}:{self.client_secret.strip()}"
        b64_auth = base64.b64encode(auth_str.encode()).decode()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    f"{self.base_url}/v1/oauth2/token",
                    data={"grant_type": "client_credentials"},
                    headers={
                        "Authorization": f"Basic {b64_auth}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
                if res.status_code == 200:
                    return res.json().get("access_token")
                if res.status_code in (401, 403):
                    logger.error(
                        "PayPal authentication failed (HTTP %s). Verify Sandbox PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in backend/.env.",
                        res.status_code,
                    )
                else:
                    logger.error("PayPal Sandbox OAuth failed with status %s", res.status_code)
                db.log_audit_event("PAYPAL_AUTH_ERROR", f"PayPal OAuth status {res.status_code}", "SYSTEM")
        except Exception as e:
            logger.error("PayPal Sandbox OAuth exception (%s): %s", type(e).__name__, e)
            db.log_audit_event("PAYPAL_AUTH_ERROR", f"Error obtaining PayPal token: {type(e).__name__}", "SYSTEM")
        return None

    @staticmethod
    def _extract_safe_error_info(res: httpx.Response) -> Dict[str, Any]:
        """Extracts non-credential PayPal error metadata for internal logs only."""
        info: Dict[str, Any] = {
            "http_status": res.status_code,
            "name": None,
            "issue": None,
            "description": None,
            "debug_id": None,
        }
        try:
            body = res.json()
            if isinstance(body, dict):
                info["name"] = body.get("name")
                info["debug_id"] = body.get("debug_id")
                details = body.get("details")
                if isinstance(details, list) and details and isinstance(details[0], dict):
                    info["issue"] = details[0].get("issue")
                    info["description"] = details[0].get("description")
                elif body.get("message"):
                    info["description"] = body.get("message")
        except Exception:
            info["description"] = (res.text or "")[:200]
        return info

    @staticmethod
    def _is_valid_redirect_url(url: Optional[str]) -> bool:
        return bool(url and (url.startswith("http://") or url.startswith("https://")))

    async def create_order(
        self,
        amount: float,
        currency: str = "USD",
        description: str = "AccessPay AI Order",
        cart: Optional[Cart] = None,
        idempotency_key: Optional[str] = None,
        return_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        token = await self.get_access_token()
        if not token:
            return {
                "success": False,
                "error": "PAYPAL_AUTH_UNAVAILABLE",
                "user_message": SAFE_PAYMENT_FAILURE_MESSAGE,
            }

        request_id = idempotency_key or str(uuid.uuid4())
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "PayPal-Request-Id": request_id,
        }

        purchase_unit = build_paypal_purchase_unit(
            amount=amount,
            currency=currency,
            description=description,
            cart=cart,
        )

        app_context: Dict[str, Any] = {
            "brand_name": "AccessPay AI (Sandbox Demo)",
            "shipping_preference": "NO_SHIPPING",
            "user_action": "PAY_NOW",
        }
        if self._is_valid_redirect_url(return_url):
            app_context["return_url"] = return_url
        if self._is_valid_redirect_url(cancel_url):
            app_context["cancel_url"] = cancel_url

        payload = {
            "intent": "CAPTURE",
            "purchase_units": [purchase_unit],
            "application_context": app_context,
        }

        endpoint = f"{self.base_url}/v2/checkout/orders"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                )
                if res.status_code in [200, 201]:
                    order_data = res.json()
                    order_id = order_data.get("id")
                    approval_url = None
                    for link in order_data.get("links", []):
                        if link.get("rel") in ["approve", "payer-action"]:
                            approval_url = link.get("href")
                            break

                    db.log_audit_event(
                        "PAYPAL_SANDBOX_ORDER_CREATED",
                        f"ID: {order_id}, Amount: ${amount:.2f}",
                        "PAYPAL"
                    )
                    return {
                        "success": True,
                        "mode": "PAYPAL_SANDBOX",
                        "provider": "paypal",
                        "environment": "sandbox",
                        "paypal_order_id": order_id,
                        "status": order_data.get("status", "CREATED"),
                        "amount": round(amount, 2),
                        "currency": currency,
                        "approval_url": approval_url,
                    }

                # Log technical PayPal error internally only (never credentials/tokens)
                err_info = self._extract_safe_error_info(res)
                logger.error(
                    "PayPal create_order failed endpoint=%s http=%s name=%s issue=%s debug_id=%s detail=%s",
                    endpoint,
                    err_info["http_status"],
                    err_info["name"],
                    err_info["issue"],
                    err_info["debug_id"],
                    err_info["description"],
                )
                db.log_audit_event(
                    "PAYPAL_CREATE_ORDER_ERROR",
                    f"HTTP {err_info['http_status']} {err_info['issue'] or err_info['name'] or ''} debug_id={err_info['debug_id']}",
                    "PAYPAL"
                )
                return {
                    "success": False,
                    "error": f"PAYPAL_HTTP_{res.status_code}",
                    "user_message": SAFE_PAYMENT_FAILURE_MESSAGE,
                }
        except Exception as e:
            logger.error("PayPal create_order exception: %s", e)
            db.log_audit_event("PAYPAL_API_ERROR", f"Failed PayPal create_order: {str(e)}", "SYSTEM")
            return {
                "success": False,
                "error": str(e),
                "user_message": SAFE_PAYMENT_FAILURE_MESSAGE,
            }

    async def get_order_status(self, paypal_order_id: str) -> Dict[str, Any]:
        token = await self.get_access_token()
        if not token:
            return {
                "success": False,
                "paypal_order_id": paypal_order_id,
                "status": "UNKNOWN",
                "error": "PAYPAL_AUTH_UNAVAILABLE",
                "provider": "paypal",
                "environment": "sandbox",
            }

        endpoint = f"{self.base_url}/v2/checkout/orders/{paypal_order_id}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(
                    endpoint,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                )
                if res.status_code == 200:
                    data = res.json()
                    pu = (data.get("purchase_units") or [{}])[0]
                    captures = pu.get("payments", {}).get("captures", [])
                    capture_id = captures[0].get("id") if captures else None
                    amt = pu.get("amount", {})
                    return {
                        "success": True,
                        "paypal_order_id": data.get("id", paypal_order_id),
                        "status": data.get("status", "UNKNOWN"),
                        "paypal_capture_id": capture_id,
                        "amount": float(amt["value"]) if amt.get("value") else None,
                        "currency": amt.get("currency_code", "USD"),
                        "provider": "paypal",
                        "environment": "sandbox",
                    }
                err_info = self._extract_safe_error_info(res)
                logger.error(
                    "PayPal get_order_status failed endpoint=%s http=%s name=%s issue=%s debug_id=%s",
                    endpoint,
                    err_info["http_status"],
                    err_info["name"],
                    err_info["issue"],
                    err_info["debug_id"],
                )
                return {
                    "success": False,
                    "paypal_order_id": paypal_order_id,
                    "status": "UNKNOWN",
                    "error": f"PAYPAL_HTTP_{res.status_code}",
                    "provider": "paypal",
                    "environment": "sandbox",
                }
        except Exception as e:
            logger.error("PayPal get_order_status exception (%s): %s", type(e).__name__, e)
            return {
                "success": False,
                "paypal_order_id": paypal_order_id,
                "status": "UNKNOWN",
                "error": str(e),
                "provider": "paypal",
                "environment": "sandbox",
            }

    async def capture_order(
        self,
        paypal_order_id: str,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        token = await self.get_access_token()
        if not token:
            return {
                "success": False,
                "error": "PAYPAL_AUTH_UNAVAILABLE",
                "user_message": SAFE_PAYMENT_FAILURE_MESSAGE,
            }

        request_id = idempotency_key or f"cap-{paypal_order_id}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "PayPal-Request-Id": request_id,
        }

        endpoint = f"{self.base_url}/v2/checkout/orders/{paypal_order_id}/capture"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    endpoint,
                    json={},
                    headers=headers,
                )
                if res.status_code in [200, 201]:
                    data = res.json()
                    status = data.get("status", "COMPLETED")
                    capture_id = None
                    purchase_units = data.get("purchase_units", [])
                    if purchase_units:
                        captures = purchase_units[0].get("payments", {}).get("captures", [])
                        if captures:
                            capture_id = captures[0].get("id")

                    if status != "COMPLETED":
                        logger.error("PayPal capture non-completed status=%s order=%s", status, paypal_order_id)
                        db.log_audit_event("PAYPAL_CAPTURE_INCOMPLETE", f"Order {paypal_order_id} status: {status}", "PAYPAL")
                        return {
                            "success": False,
                            "error": f"CAPTURE_STATUS_{status}",
                            "user_message": SAFE_PAYMENT_FAILURE_MESSAGE,
                        }

                    db.log_audit_event(
                        "PAYPAL_SANDBOX_CAPTURED",
                        f"Order ID: {paypal_order_id}, Capture ID: {capture_id}",
                        "PAYPAL"
                    )
                    return {
                        "success": True,
                        "mode": "PAYPAL_SANDBOX",
                        "provider": "paypal",
                        "environment": "sandbox",
                        "paypal_order_id": paypal_order_id,
                        "paypal_capture_id": capture_id,
                        "status": "COMPLETED",
                    }

                # Log raw PayPal error (e.g. UNPROCESSABLE_ENTITY / ORDER_NOT_APPROVED) in backend logs only
                err_info = self._extract_safe_error_info(res)
                logger.error(
                    "PayPal capture_order failed endpoint=%s http=%s name=%s issue=%s debug_id=%s detail=%s",
                    endpoint,
                    err_info["http_status"],
                    err_info["name"],
                    err_info["issue"],
                    err_info["debug_id"],
                    err_info["description"],
                )
                db.log_audit_event(
                    "PAYPAL_CAPTURE_ERROR",
                    f"Order {paypal_order_id} HTTP {err_info['http_status']} {err_info['issue'] or err_info['name'] or ''} debug_id={err_info['debug_id']}",
                    "PAYPAL"
                )
                return {
                    "success": False,
                    "error": f"PAYPAL_CAPTURE_HTTP_{res.status_code}",
                    "user_message": SAFE_PAYMENT_FAILURE_MESSAGE,
                }
        except Exception as e:
            logger.error("PayPal capture_order exception: %s", e)
            db.log_audit_event("PAYPAL_CAPTURE_ERROR", f"PayPal capture failed: {str(e)}", "SYSTEM")
            return {
                "success": False,
                "error": str(e),
                "user_message": SAFE_PAYMENT_FAILURE_MESSAGE,
            }


class PaymentService:
    """
    Unified Payment Service Facade:
    - Preserves PaymentService abstraction.
    - Delegates to PayPalPaymentService or MockPaymentService based on PAYMENT_PROVIDER.
    - Enforces idempotency and duplicate-payment locks so repeated clicks, voice commands,
      Enter presses, or switch activations never create multiple orders or captures.
    """
    def __init__(self):
        self.paypal_service = PayPalPaymentService()
        self.mock_service = MockPaymentService()
        self.provider_config = settings.PAYMENT_PROVIDER.lower()  # 'paypal', 'mock', 'auto'
        self.mode = "sandbox"
        self._simulate_failure = False

        # Idempotency & duplicate-submission protection state
        self._orders_by_key: Dict[str, Dict[str, Any]] = {}
        self._captured_orders: Dict[str, Dict[str, Any]] = {}
        self._in_flight_creates: Set[str] = set()
        self._in_flight_captures: Set[str] = set()

    def is_paypal_configured(self) -> bool:
        return self.paypal_service.is_configured()

    def set_provider(self, provider: str):
        if provider.lower() in ["paypal", "mock", "auto"]:
            self.provider_config = provider.lower()

    def get_active_provider(self) -> str:
        if self.provider_config == "mock":
            return "mock"
        if self.provider_config == "paypal":
            return "paypal"
        return "paypal" if self.is_paypal_configured() else "mock"

    def set_simulate_failure(self, simulate: bool):
        """Allows testing graceful payment failure handling."""
        self._simulate_failure = simulate

    def reset_idempotency_state(self):
        self._orders_by_key.clear()
        self._captured_orders.clear()
        self._in_flight_creates.clear()
        self._in_flight_captures.clear()
        self._simulate_failure = False

    async def get_access_token(self) -> Optional[str]:
        return await self.paypal_service.get_access_token()

    async def create_order(
        self,
        amount: float,
        currency: str = "USD",
        description: str = "AccessPay AI Order",
        cart: Optional[Cart] = None,
        idempotency_key: Optional[str] = None,
        return_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Server-controlled PayPal Sandbox Order creation with idempotency protection.
        """
        if self._simulate_failure:
            db.log_audit_event("PAYPAL_SIMULATED_FAILURE", "Payment rejected via simulated gateway decline", "DEMO")
            return {
                "success": False,
                "error": "Payment gateway declined transaction (simulated)",
                "user_message": SAFE_PAYMENT_FAILURE_MESSAGE,
            }

        # Idempotency & duplicate-submit protection
        if idempotency_key:
            if idempotency_key in self._in_flight_creates:
                db.log_audit_event("DUPLICATE_CREATE_BLOCKED", f"Concurrent order creation blocked for {idempotency_key}", "SYSTEM")
                return {
                    "success": False,
                    "duplicate": True,
                    "error": "DUPLICATE_ORDER_IN_FLIGHT",
                    "user_message": "Processing payment...",
                }
            if idempotency_key in self._orders_by_key:
                existing = self._orders_by_key[idempotency_key]
                db.log_audit_event("IDEMPOTENT_ORDER_RETURNED", f"Returning existing order {existing.get('paypal_order_id')} for {idempotency_key}", "SYSTEM")
                return {**existing, "idempotent_reused": True}

            self._in_flight_creates.add(idempotency_key)

        try:
            active_provider = self.get_active_provider()
            if active_provider == "paypal":
                res = await self.paypal_service.create_order(
                    amount=amount,
                    currency=currency,
                    description=description,
                    cart=cart,
                    idempotency_key=idempotency_key,
                    return_url=return_url,
                    cancel_url=cancel_url,
                )
                # Automatic fallback to MockPaymentService if in 'auto' mode and live network is unreachable
                if not res.get("success") and self.provider_config == "auto":
                    logger.warning("PayPal live sandbox unreachable in auto mode; using MockPaymentService fallback.")
                    res = await self.mock_service.create_order(
                        amount=amount,
                        currency=currency,
                        description=description,
                        cart=cart,
                        idempotency_key=idempotency_key,
                    )
            else:
                res = await self.mock_service.create_order(
                    amount=amount,
                    currency=currency,
                    description=description,
                    cart=cart,
                    idempotency_key=idempotency_key,
                )

            if res.get("success") and idempotency_key:
                self._orders_by_key[idempotency_key] = res

            return res
        finally:
            if idempotency_key:
                self._in_flight_creates.discard(idempotency_key)

    async def capture_order(
        self,
        paypal_order_id: str,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Captures an approved PayPal Sandbox order with duplicate-capture protection.
        """
        if self._simulate_failure:
            self._simulate_failure = False  # Reset after one simulated failure so 'Try Again' works cleanly
            db.log_audit_event("PAYPAL_SIMULATED_CAPTURE_FAILURE", f"Simulated capture failure for {paypal_order_id}", "DEMO")
            return {
                "success": False,
                "error": "Capture failure simulated",
                "user_message": SAFE_PAYMENT_FAILURE_MESSAGE,
            }

        # Duplicate capture protection
        if paypal_order_id in self._in_flight_captures:
            db.log_audit_event("DUPLICATE_CAPTURE_BLOCKED", f"Concurrent capture blocked for {paypal_order_id}", "SYSTEM")
            return {
                "success": False,
                "duplicate": True,
                "error": "DUPLICATE_CAPTURE_IN_FLIGHT",
                "user_message": "Processing payment...",
            }

        if paypal_order_id in self._captured_orders:
            db.log_audit_event("DUPLICATE_CAPTURE_PREVENTED", f"Order {paypal_order_id} was already captured", "SYSTEM")
            return {
                "success": False,
                "duplicate": True,
                "already_captured": True,
                "error": "ORDER_ALREADY_CAPTURED",
                "user_message": "This payment has already been processed.",
            }

        self._in_flight_captures.add(paypal_order_id)
        try:
            if paypal_order_id.startswith("PAYID-SBX-") or self.get_active_provider() == "mock":
                res = await self.mock_service.capture_order(paypal_order_id, idempotency_key=idempotency_key)
            else:
                res = await self.paypal_service.capture_order(paypal_order_id, idempotency_key=idempotency_key)

            if res.get("success"):
                self._captured_orders[paypal_order_id] = res
            return res
        finally:
            self._in_flight_captures.discard(paypal_order_id)

    async def get_order_status(self, paypal_order_id: str) -> Dict[str, Any]:
        if paypal_order_id.startswith("PAYID-SBX-") or self.get_active_provider() == "mock":
            return await self.mock_service.get_order_status(paypal_order_id)
        return await self.paypal_service.get_order_status(paypal_order_id)


payment_service = PaymentService()
mock_payment_service = payment_service.mock_service
paypal_payment_service = payment_service.paypal_service
