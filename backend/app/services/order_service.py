import datetime
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional
from app.db.database import db
from app.models.analytics import OrderLineItem, OrderRecord
from app.services.cart_service import cart_service
from app.services.accessibility_service import accessibility_service


class OrderService:
    @staticmethod
    def build_order_line_items(cart) -> List[OrderLineItem]:
        order_items: List[OrderLineItem] = []
        for item in cart.items:
            unit_dec = Decimal(str(item.product.price)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            line_dec = (unit_dec * item.quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            variant_text = (
                ", ".join(f"{k}: {v}" for k, v in item.selected_variant.items())
                if item.selected_variant
                else "Standard Option"
            )
            order_items.append(
                OrderLineItem(
                    product_id=item.product_id,
                    product_title=item.product.title,
                    merchant=item.product.merchant,
                    category=item.product.category,
                    unit_price=float(unit_dec),
                    quantity=item.quantity,
                    line_total=float(line_dec),
                    variant=variant_text,
                )
            )
        return order_items

    @staticmethod
    def summarize_cart_metadata(cart) -> Dict[str, Any]:
        first_item = cart.items[0] if cart.items else None
        first_product = first_item.product if first_item else None
        if len(cart.items) > 1 and first_product:
            product_title = f"{first_product.title} (+{len(cart.items) - 1} more)"
            unique_merchants = list(dict.fromkeys(i.product.merchant for i in cart.items if i.product.merchant))
            merchant = ", ".join(unique_merchants) if unique_merchants else "Verified Merchant"
        else:
            product_title = first_product.title if first_product else "Miscellaneous AccessPay Order"
            merchant = first_product.merchant if first_product else "Verified Merchant"
        category = first_product.category if first_product else "General"
        is_recurring = cart.has_subscriptions or cart.has_trials
        return {
            "product_title": product_title,
            "merchant": merchant,
            "category": category,
            "is_recurring": is_recurring,
        }

    def create_order_from_cart(
        self,
        paypal_order_id: str,
        confirmation_method: str = "VOICE",
        paypal_capture_id: Optional[str] = None,
        interaction_mode: Optional[str] = None
    ) -> OrderRecord:
        cart = cart_service.get_cart()
        prefs = accessibility_service.get_preferences()
        
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        now_date = now_dt.strftime("%Y-%m-%d")
        now_timestamp = now_dt.isoformat()
        order_num = f"ORD-{uuid.uuid4().hex[:5].upper()}"

        order_items = self.build_order_line_items(cart)
        meta = self.summarize_cart_metadata(cart)
        variant_str = (
            "Multiple items"
            if len(order_items) > 1
            else (order_items[0].variant if order_items else "Standard Option")
        )

        order = OrderRecord(
            order_id=order_num,
            date=now_date,
            timestamp=now_timestamp,
            product_title=meta["product_title"],
            merchant=meta["merchant"],
            category=meta["category"],
            item_price=cart.subtotal,
            item_subtotal=cart.subtotal,
            shipping=cart.shipping_total,
            tax=cart.tax_total,
            total=cart.total_today,
            quantity=cart.item_count,
            variant=variant_str,
            items=order_items,
            is_recurring=meta["is_recurring"],
            interaction_mode=interaction_mode or prefs.current_mode,
            confirmation_method=confirmation_method,
            payment_status="PAID",
            paypal_order_id=paypal_order_id,
            paypal_capture_id=paypal_capture_id,
            tracking_status="PROCESSING",
            tracking_number=f"1Z{uuid.uuid4().hex[:16].upper()}",
            return_eligible=not meta["is_recurring"],
            return_window_days=30
        )

        db.save_order(order.model_dump())
        # Clear cart after confirmed order without triggering checkout-invalidation warning
        cart_service.clear(notify_invalidation=False)
        return order

    def get_all_orders(self) -> List[OrderRecord]:
        raw = db.get_all_orders()
        orders = [OrderRecord(**o) for o in raw]
        orders.sort(key=lambda o: (o.timestamp or f"{o.date}T00:00:00"), reverse=True)
        return orders

    def get_order_by_id(self, order_id: str) -> Optional[OrderRecord]:
        return next((o for o in self.get_all_orders() if o.order_id.lower() == order_id.lower()), None)

    def query_orders_conversational(self, user_text: str) -> Dict[str, Any]:
        """Answer order-history questions strictly from stored SQLite orders (never calls Channel3)."""
        orders = self.get_all_orders()
        t = user_text.lower().strip()
        if not orders:
            return {
                "orders": [],
                "selected_order": None,
                "message": "You have no completed orders in your Order History yet.",
            }

        # Check merchant filter: "what did I buy from [merchant]?"
        import re
        merchant_match = re.search(r"\bfrom\s+([a-z0-9 &'\.-]+?)(?:\?|$)", t)
        if merchant_match:
            target_merchant = merchant_match.group(1).strip()
            filtered = [
                o for o in orders
                if target_merchant in o.merchant.lower()
                or any(target_merchant in li.merchant.lower() for li in (o.items or []))
            ]
            if not filtered:
                return {
                    "orders": [],
                    "selected_order": None,
                    "message": f"I didn't find any completed orders from '{merchant_match.group(1).strip()}' in your Order History.",
                }
            lines = [f"- {o.order_id} ({o.date}): {o.product_title} — ${o.total:.2f} [{o.payment_status}]" for o in filtered[:5]]
            return {
                "orders": [o.model_dump() for o in filtered],
                "selected_order": filtered[0].model_dump(),
                "message": f"Orders from {merchant_match.group(1).strip()}:\n" + "\n".join(lines),
            }

        # Last / latest order query
        if any(p in t for p in ("last order", "latest order", "recent order", "how much was my last")):
            latest = orders[0]
            if latest.items and len(latest.items) > 1:
                items_desc = ", ".join(f"{li.product_title} (x{li.quantity})" for li in latest.items)
            else:
                items_desc = latest.product_title
            pp_note = f" PayPal Order: {latest.paypal_order_id}." if latest.paypal_order_id else ""
            msg = (
                f"Your last order ({latest.order_id} on {latest.date}) was {items_desc} "
                f"from {latest.merchant} for ${latest.total:.2f} ({latest.payment_status}).{pp_note}"
            )
            return {
                "orders": [o.model_dump() for o in orders],
                "selected_order": latest.model_dump(),
                "message": msg,
            }

        lines = [
            f"- {o.order_id} ({o.date}): {o.product_title} from {o.merchant} — ${o.total:.2f} ({o.payment_status})"
            for o in orders[:5]
        ]
        msg = f"You have {len(orders)} completed order{'s' if len(orders) != 1 else ''}:\n" + "\n".join(lines)
        return {
            "orders": [o.model_dump() for o in orders],
            "selected_order": orders[0].model_dump(),
            "message": msg,
        }

    async def reorder_order(self, order_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Safely prepares a new checkout cart & fresh PurchaseReview from a historical order:
        refreshes current product pricing when practical, clears stale confirmation state,
        and NEVER reuses previous payment authorization.
        """
        from app.models.product import Product
        from app.services.confirmation_service import confirmation_service
        from app.services.product_service import product_service

        orders = self.get_all_orders()
        if not orders:
            raise ValueError("No completed orders found to reorder.")
        target = self.get_order_by_id(order_id) if order_id else orders[0]
        if not target:
            raise ValueError(f"Order {order_id} not found.")

        historical_items = target.items or []
        if not historical_items:
            from app.models.analytics import OrderLineItem
            qty = max(1, int(target.quantity or 1))
            unit = round(float(target.item_price or target.total) / qty, 2)
            historical_items = [
                OrderLineItem(
                    product_id=f"reorder_{target.order_id.lower()}",
                    product_title=target.product_title,
                    merchant=target.merchant,
                    category=target.category,
                    unit_price=unit,
                    quantity=qty,
                    line_total=round(unit * qty, 2),
                    variant=target.variant or "Standard Option",
                )
            ]

        # Build fresh cart & reset any old confirmation/review state
        confirmation_service.reset()
        cart_service.clear(notify_invalidation=False)
        price_changes: List[Dict[str, Any]] = []

        for li in historical_items:
            live_product = product_service.get_product_by_id(li.product_id)
            if (
                product_service.get_active_provider_mode() == "channel3"
                and product_service.channel3_service.is_configured()
            ):
                try:
                    hits = await product_service.channel3_service.search(
                        query=li.product_title,
                        limit=6,
                        force_refresh=True,
                    )
                    matched = next((p for p in hits if p.id == li.product_id), None)
                    if matched:
                        live_product = matched
                except Exception:
                    pass

            if not live_product:
                live_product = Product(
                    id=li.product_id,
                    title=li.product_title,
                    description=f"Reorder item from {target.order_id}",
                    price=li.unit_price,
                    shipping=0.0,
                    estimated_tax=round(li.unit_price * 0.08, 2),
                    category=li.category or "General",
                    merchant=li.merchant or "Verified Merchant",
                )
            product_service.channel3_service.cached_by_id[live_product.id] = live_product

            if round(float(live_product.price), 2) != round(float(li.unit_price), 2):
                price_changes.append(
                    {
                        "product_id": live_product.id,
                        "title": live_product.title,
                        "old_price": round(float(li.unit_price), 2),
                        "current_price": round(float(live_product.price), 2),
                    }
                )

            variant_dict = None
            if li.variant and li.variant not in ("Standard", "Standard Option", "Multiple items"):
                variant_dict = {"Option": li.variant}
            cart_service.add_item(live_product.id, quantity=li.quantity, variant=variant_dict)

        review = confirmation_service.prepare_payment_review()
        db.log_audit_event(
            "ORDER_REORDER_PREPARED",
            f"Prepared fresh review {review.review_token} from historical order {target.order_id} (${review.total_today:.2f})",
            "USER",
        )
        return {
            "success": True,
            "source_order_id": target.order_id,
            "review": review.model_dump(),
            "cart": review.cart.model_dump(),
            "price_changes": price_changes,
            "requires_fresh_confirmation": True,
        }

    def track_order(self, query: Optional[str] = None) -> Dict[str, Any]:
        orders = self.get_all_orders()
        if not orders:
            return {
                "message": "You have no active orders to track.",
                "orders": []
            }

        latest = orders[0]
        status_steps = [
            {"step": "ORDER PLACED", "completed": True},
            {"step": "PROCESSING", "completed": latest.tracking_status in ["PROCESSING", "SHIPPED", "DELIVERED"]},
            {"step": "SHIPPED", "completed": latest.tracking_status in ["SHIPPED", "DELIVERED"]},
            {"step": "DELIVERED", "completed": latest.tracking_status == "DELIVERED"}
        ]

        return {
            "message": f"Your latest order for '{latest.product_title}' is {latest.tracking_status}. Tracking number: {latest.tracking_number}.",
            "latest_order": latest.model_dump(),
            "tracking_timeline": status_steps
        }

    def return_assistant(self, product_name: str = "headphones") -> Dict[str, Any]:
        orders = self.get_all_orders()
        matching = [o for o in orders if product_name.lower() in o.product_title.lower()]
        
        if not matching:
            return {
                "found": False,
                "message": f"I couldn't locate a previous order for '{product_name}'. Would you like me to display all recent purchases?"
            }

        target = matching[0]
        if not target.return_eligible:
            return {
                "found": True,
                "eligible": False,
                "message": f"Order {target.order_id} for '{target.product_title}' is a recurring subscription or digital service and is not eligible for physical return."
            }

        return {
            "found": True,
            "eligible": True,
            "order_id": target.order_id,
            "product": target.product_title,
            "merchant": target.merchant,
            "return_window_remaining": f"{target.return_window_days} days",
            "instructions": [
                f"Merchant {target.merchant} offers prepaid return drop-off with QR code (no printer needed).",
                "UPS will scan your phone code and pack the item for you.",
                "Refund will be issued directly back to your PayPal balance within 3-5 business days of drop-off."
            ],
            "message": f"Good news! Order {target.order_id} ({target.product_title}) is eligible for return. Prepaid UPS drop-off is supported without needing to pack or print labels."
        }


order_service = OrderService()
