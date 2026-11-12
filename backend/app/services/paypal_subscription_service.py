import datetime
import logging
import uuid
from typing import Any, Dict, List, Optional
import httpx
from app.config import settings
from app.db.database import db
from app.models.subscription import SubscriptionOffer, SubscriptionRecord
from app.services.payment_service import (
    SANDBOX_BASE_URL,
    payment_service,
)

logger = logging.getLogger("accesspay.paypal_subscription")


class PayPalSubscriptionService:
    """
    Real PayPal Sandbox Subscriptions API v1 client:
      1. POST /v1/catalogs/products
      2. POST /v1/billing/plans
      3. POST /v1/billing/subscriptions
      4. GET  /v1/billing/subscriptions/{subscription_id}
      5. POST /v1/billing/subscriptions/{subscription_id}/cancel

    Never uses live credentials and never exposes PAYPAL_CLIENT_SECRET.
    """

    def __init__(self):
        self.base_url = SANDBOX_BASE_URL

    def is_sandbox_configured(self) -> bool:
        return bool(
            settings.PAYPAL_CLIENT_ID.strip()
            and settings.PAYPAL_CLIENT_SECRET.strip()
        )

    async def _get_token(self) -> Optional[str]:
        return await payment_service.get_access_token()

    async def ensure_product_and_plan(self, offer: SubscriptionOffer) -> Dict[str, str]:
        """Creates or reuses cached Sandbox Catalog Product & Billing Plan IDs for the offer."""
        cached = db.get_paypal_catalog_cache(offer.id)
        if cached and cached.get("paypal_product_id") and cached.get("paypal_plan_id"):
            return {
                "paypal_product_id": cached["paypal_product_id"],
                "paypal_plan_id": cached["paypal_plan_id"],
            }

        token = await self._get_token()
        if not token:
            raise RuntimeError("PayPal Sandbox authentication unavailable.")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            # Step 1: Create Catalog Product
            prod_payload = {
                "name": offer.name[:127],
                "description": offer.description[:256],
                "type": "SERVICE",
                "category": "SOFTWARE",
            }
            prod_res = await client.post(
                f"{self.base_url}/v1/catalogs/products",
                json=prod_payload,
                headers={**headers, "PayPal-Request-Id": f"prod-{offer.id}-{uuid.uuid4().hex[:8]}"},
            )
            if prod_res.status_code not in (200, 201):
                logger.warning("PayPal product creation failed: status=%s", prod_res.status_code)
                raise RuntimeError("Unable to register PayPal Sandbox product.")
            paypal_product_id = prod_res.json().get("id")
            if not paypal_product_id:
                raise RuntimeError("PayPal Sandbox did not return a product ID.")

            # Step 2: Create Billing Plan
            plan_payload = {
                "product_id": paypal_product_id,
                "name": offer.name[:127],
                "description": f"Billed ${offer.recurring_amount:.2f} {offer.billing_frequency}"[:127],
                "status": "ACTIVE",
                "billing_cycles": [
                    {
                        "frequency": {
                            "interval_unit": offer.billing_interval,
                            "interval_count": offer.interval_count,
                        },
                        "tenure_type": "REGULAR",
                        "sequence": 1,
                        "total_cycles": 0,
                        "pricing_scheme": {
                            "fixed_price": {
                                "value": f"{offer.recurring_amount:.2f}",
                                "currency_code": offer.currency,
                            }
                        },
                    }
                ],
                "payment_preferences": {
                    "auto_bill_outstanding": True,
                    "setup_fee_failure_action": "CONTINUE",
                    "payment_failure_threshold": 3,
                },
            }
            plan_res = await client.post(
                f"{self.base_url}/v1/billing/plans",
                json=plan_payload,
                headers={**headers, "PayPal-Request-Id": f"plan-{offer.id}-{uuid.uuid4().hex[:8]}"},
            )
            if plan_res.status_code not in (200, 201):
                logger.warning("PayPal plan creation failed: status=%s", plan_res.status_code)
                raise RuntimeError("Unable to create PayPal Sandbox billing plan.")
            paypal_plan_id = plan_res.json().get("id")
            if not paypal_plan_id:
                raise RuntimeError("PayPal Sandbox did not return a plan ID.")

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        db.save_paypal_catalog_cache(offer.id, paypal_product_id, paypal_plan_id, now)
        return {
            "paypal_product_id": paypal_product_id,
            "paypal_plan_id": paypal_plan_id,
        }

    async def create_subscription(
        self,
        offer: SubscriptionOffer,
        return_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> SubscriptionRecord:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if not self.is_sandbox_configured():
            # Deterministic offline fallback ONLY when PayPal Sandbox keys are not configured
            sub_id = f"I-SBXDEMO{uuid.uuid4().hex[:8].upper()}"
            record = SubscriptionRecord(
                subscription_id=sub_id,
                offer_id=offer.id,
                plan_name=offer.name,
                provider=offer.provider,
                currency=offer.currency,
                amount_due_today=offer.amount_due_today,
                recurring_amount=offer.recurring_amount,
                billing_frequency=offer.billing_frequency,
                paypal_product_id=f"PROD-DEMO-{offer.id}",
                paypal_plan_id=f"P-DEMO-{offer.id}",
                paypal_subscription_id=sub_id,
                status="ACTIVE",
                approval_url=None,
                created_at=now,
                updated_at=now,
                is_demo_catalog=offer.is_demo,
                paypal_environment="sandbox_offline_fallback",
            )
            db.save_subscription(record.model_dump())
            return record

        ids = await self.ensure_product_and_plan(offer)
        token = await self._get_token()
        if not token:
            raise RuntimeError("PayPal Sandbox authentication unavailable.")

        app_context: Dict[str, Any] = {
            "brand_name": "AccessPay AI (Sandbox Demo)",
            "locale": "en-US",
            "shipping_preference": "NO_SHIPPING",
            "user_action": "SUBSCRIBE_NOW",
        }
        if payment_service.paypal_service._is_valid_redirect_url(return_url):
            app_context["return_url"] = return_url
        if payment_service.paypal_service._is_valid_redirect_url(cancel_url):
            app_context["cancel_url"] = cancel_url

        payload = {
            "plan_id": ids["paypal_plan_id"],
            "application_context": app_context,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(
                f"{self.base_url}/v1/billing/subscriptions",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                    "PayPal-Request-Id": f"sub-{uuid.uuid4().hex[:12]}",
                },
            )

        if res.status_code not in (200, 201):
            logger.warning("PayPal create subscription failed: status=%s body=%s", res.status_code, (res.text or "")[:300])
            raise RuntimeError("Could not initiate PayPal Sandbox subscription.")

        data = res.json()
        pp_sub_id = data.get("id")
        if not pp_sub_id:
            raise RuntimeError("PayPal Sandbox did not return a subscription ID.")
        approve_url = next(
            (lnk.get("href") for lnk in data.get("links", []) if lnk.get("rel") == "approve"),
            None,
        )

        record = SubscriptionRecord(
            subscription_id=pp_sub_id,
            offer_id=offer.id,
            plan_name=offer.name,
            provider=offer.provider,
            currency=offer.currency,
            amount_due_today=offer.amount_due_today,
            recurring_amount=offer.recurring_amount,
            billing_frequency=offer.billing_frequency,
            paypal_product_id=ids["paypal_product_id"],
            paypal_plan_id=ids["paypal_plan_id"],
            paypal_subscription_id=pp_sub_id,
            status=data.get("status", "APPROVAL_PENDING"),
            approval_url=approve_url,
            created_at=now,
            updated_at=now,
            is_demo_catalog=offer.is_demo,
            paypal_environment="sandbox",
        )
        db.save_subscription(record.model_dump())
        db.log_audit_event("PAYPAL_SUBSCRIPTION_CREATED", f"Created Sandbox subscription {pp_sub_id}", "SYSTEM")
        return record

    async def get_subscription_status(self, subscription_id: str) -> SubscriptionRecord:
        existing_dict = db.get_subscription(subscription_id)
        if not existing_dict:
            raise ValueError("Subscription not found.")
        record = SubscriptionRecord(**existing_dict)

        if not self.is_sandbox_configured() or record.paypal_environment == "sandbox_offline_fallback":
            return record

        token = await self._get_token()
        if not token:
            return record

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                f"{self.base_url}/v1/billing/subscriptions/{subscription_id}",
                headers={"Authorization": f"Bearer {token}"},
            )

        if res.status_code == 200:
            data = res.json()
            pp_status = data.get("status")
            if pp_status:
                record.status = pp_status
                record.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
                db.save_subscription(record.model_dump())

        return record

    async def cancel_subscription(self, subscription_id: str, reason: str = "User requested cancellation") -> SubscriptionRecord:
        existing_dict = db.get_subscription(subscription_id)
        if not existing_dict:
            raise ValueError("Subscription not found.")
        record = SubscriptionRecord(**existing_dict)

        if (
            self.is_sandbox_configured()
            and record.paypal_environment == "sandbox"
            and record.status != "APPROVAL_PENDING"
        ):
            token = await self._get_token()
            if not token:
                raise RuntimeError("PayPal Sandbox authentication unavailable.")
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    f"{self.base_url}/v1/billing/subscriptions/{subscription_id}/cancel",
                    json={"reason": reason[:128]},
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                )
            if res.status_code not in (200, 204):
                logger.warning("PayPal subscription cancel failed: status=%s", res.status_code)
                raise RuntimeError("Unable to cancel PayPal Sandbox subscription right now.")

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        record.status = "CANCELLED"
        record.cancelled_at = now
        record.updated_at = now
        db.save_subscription(record.model_dump())
        db.log_audit_event("PAYPAL_SUBSCRIPTION_CANCELLED", f"Cancelled subscription {subscription_id}", "USER")
        return record

    @staticmethod
    def list_subscriptions() -> List[SubscriptionRecord]:
        return [SubscriptionRecord(**row) for row in db.get_all_subscriptions()]


paypal_subscription_service = PayPalSubscriptionService()
