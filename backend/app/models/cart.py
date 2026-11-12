from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from app.models.product import Product


class CartItem(BaseModel):
    id: str
    product_id: str
    product: Product
    quantity: int = 1
    selected_variant: Dict[str, str] = Field(default_factory=dict)
    item_total: float = 0.0


class Cart(BaseModel):
    items: List[CartItem] = Field(default_factory=list)
    item_count: int = 0
    subtotal: float = 0.0
    shipping_total: float = 0.0
    tax_total: float = 0.0
    discount_total: float = 0.0
    total_today: float = 0.0
    future_payments: Optional[str] = "None"
    has_subscriptions: bool = False
    has_trials: bool = False
    warnings: List[str] = Field(default_factory=list)


class AddToCartRequest(BaseModel):
    product_id: str
    quantity: int = 1
    selected_variant: Optional[Dict[str, str]] = None


class UpdateCartItemRequest(BaseModel):
    quantity: int


class RemoveCartItemRequest(BaseModel):
    product_id_or_title: str
