from decimal import Decimal, ROUND_HALF_UP
from typing import Callable, Dict, List, Optional
from app.models.cart import Cart, CartItem
from app.models.product import Product
from app.services.product_service import product_service
from app.services.accessibility_service import accessibility_service
from app.db.database import db

_CENT = Decimal("0.01")


def _to_dec(value: float | int | str | Decimal) -> Decimal:
    return Decimal(str(value or 0))


def _round_cents(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


class CartService:
    def __init__(self):
        self._items: Dict[str, CartItem] = {}
        self._change_callbacks: List[Callable[[str], None]] = []

    def register_change_callback(self, callback: Callable[[str], None]) -> None:
        if callback not in self._change_callbacks:
            self._change_callbacks.append(callback)

    def _notify_cart_changed(self, reason: str) -> None:
        for cb in self._change_callbacks:
            cb(reason)

    def get_cart(self) -> Cart:
        prefs = accessibility_service.get_preferences()
        items_list = list(self._items.values())

        subtotal_dec = Decimal("0.00")
        shipping_dec = Decimal("0.00")
        tax_dec = Decimal("0.00")
        for item in items_list:
            unit_dec = _round_cents(_to_dec(item.product.price))
            line_total_dec = _round_cents(unit_dec * item.quantity)
            item.item_total = float(line_total_dec)
            subtotal_dec += line_total_dec
            shipping_dec += _round_cents(_to_dec(item.product.shipping))
            tax_dec += _round_cents(_round_cents(_to_dec(item.product.estimated_tax)) * item.quantity)

        discount_dec = Decimal("0.00")
        subtotal = float(_round_cents(subtotal_dec))
        shipping_total = float(_round_cents(shipping_dec))
        tax_total = float(_round_cents(tax_dec))
        discount_total = float(_round_cents(discount_dec))
        total_today = float(_round_cents(subtotal_dec + shipping_dec + tax_dec - discount_dec))
        
        has_subscriptions = any(item.product.is_subscription and not item.product.is_trial for item in items_list)
        has_trials = any(item.product.is_trial for item in items_list)

        future_payments = "None"
        if has_trials:
            trial_item = next(item for item in items_list if item.product.is_trial)
            future_payments = f"${trial_item.product.trial_post_price:.2f}/month after {trial_item.product.trial_days}-day free trial"
        elif has_subscriptions:
            sub_item = next(item for item in items_list if item.product.is_subscription)
            future_payments = f"${sub_item.product.price:.2f} every {sub_item.product.subscription_period or 'month'} until cancelled"

        warnings: List[str] = []
        if prefs.warn_quantity_greater_one:
            for item in items_list:
                if item.quantity > 1:
                    warnings.append(f"Notice: You are purchasing {item.quantity} units of '{item.product.title}'.")
        
        if shipping_total > prefs.warn_shipping_exceeds:
            warnings.append(f"Notice: Shipping charge is ${shipping_total:.2f}, which exceeds your ${prefs.warn_shipping_exceeds:.2f} preference limit.")

        if has_subscriptions:
            warnings.append("Subscription Guardian: This order contains recurring billing. Explicit acknowledgement required before payment.")
            
        if has_trials:
            warnings.append("Trial Guardian: Free trial will automatically renew at monthly rate unless cancelled.")

        return Cart(
            items=items_list,
            item_count=sum(i.quantity for i in items_list),
            subtotal=subtotal,
            shipping_total=shipping_total,
            tax_total=tax_total,
            discount_total=discount_total,
            total_today=total_today,
            future_payments=future_payments,
            has_subscriptions=has_subscriptions,
            has_trials=has_trials,
            warnings=warnings
        )

    def add_item(self, product_id: str, quantity: int = 1, variant: Optional[Dict[str, str]] = None) -> Cart:
        product = product_service.get_product_by_id(product_id)
        if not product:
            raise ValueError(f"Product {product_id} not found")
        qty = max(1, int(quantity))
        unit_dec = _round_cents(_to_dec(product.price))

        if product_id in self._items:
            existing = self._items[product_id]
            existing.quantity += qty
            if variant:
                existing.selected_variant = {**existing.selected_variant, **variant}
            existing.item_total = float(_round_cents(unit_dec * existing.quantity))
        else:
            self._items[product_id] = CartItem(
                id=f"item_{product_id}",
                product_id=product_id,
                product=product,
                quantity=qty,
                selected_variant=variant or {},
                item_total=float(_round_cents(unit_dec * qty))
            )

        db.log_audit_event("CART_ITEM_ADDED", f"Added {qty}x {product.title} to cart", "USER")
        self._notify_cart_changed("The cart items or quantities changed.\n\nPlease review the updated total.")
        return self.get_cart()

    def remove_item(self, product_id_or_title: str) -> Cart:
        # Search by ID or title
        target_id = None
        for pid, item in self._items.items():
            if pid == product_id_or_title or product_id_or_title.lower() in item.product.title.lower():
                target_id = pid
                break

        if target_id and target_id in self._items:
            removed = self._items.pop(target_id)
            db.log_audit_event("CART_ITEM_REMOVED", f"Removed {removed.product.title} from cart", "USER")
            self._notify_cart_changed("An item was removed from your cart.\n\nPlease review the updated total.")

        return self.get_cart()

    def update_quantity(self, product_id: str, quantity: int) -> Cart:
        if product_id in self._items:
            if quantity <= 0:
                return self.remove_item(product_id)
            item = self._items[product_id]
            old_qty = item.quantity
            item.quantity = quantity
            unit_dec = _round_cents(_to_dec(item.product.price))
            item.item_total = float(_round_cents(unit_dec * quantity))
            db.log_audit_event("CART_QUANTITY_UPDATED", f"Set {product_id} quantity to {quantity}", "USER")
            self._notify_cart_changed(
                f"The item quantity changed from {old_qty} to {quantity}.\n\nPlease review the updated total."
            )
        return self.get_cart()

    def clear(self, notify_invalidation: bool = True) -> Cart:
        had_items = bool(self._items)
        self._items.clear()
        db.log_audit_event("CART_CLEARED", "Cleared all cart contents", "USER")
        if had_items and notify_invalidation:
            self._notify_cart_changed("The cart was cleared.")
        return self.get_cart()


cart_service = CartService()
