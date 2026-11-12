from pydantic import BaseModel, Field
from typing import List, Optional


class AccessibilityActivitySummary(BaseModel):
    purchases_completed: int = 14
    voice_interactions: int = 42
    keyboard_interactions: int = 31
    large_control_interactions: int = 19
    switch_compatible_interactions: int = 12
    subscription_warnings_shown: int = 8
    cheaper_alternatives_accepted: int = 6
    purchases_cancelled_before_payment: int = 5  # Kept as intentional user cancellation, not a mistake!


class OrderLineItem(BaseModel):
    product_id: str
    product_title: str
    merchant: str
    category: str = "General"
    unit_price: float
    quantity: int = 1
    line_total: float
    variant: Optional[str] = "Standard Option"


class OrderRecord(BaseModel):
    order_id: str
    date: str
    timestamp: Optional[str] = None
    product_title: str
    merchant: str
    category: str
    item_price: float
    item_subtotal: Optional[float] = None
    shipping: float
    tax: float
    total: float
    quantity: int = 1
    variant: Optional[str] = "Standard"
    items: List[OrderLineItem] = Field(default_factory=list)
    is_recurring: bool = False
    interaction_mode: str = "VOICE"
    confirmation_method: str = "Exact-Amount Voice Phrase"
    payment_status: str = "PAID"
    paypal_order_id: Optional[str] = None
    paypal_capture_id: Optional[str] = None
    tracking_status: str = "DELIVERED"
    tracking_number: Optional[str] = None
    return_eligible: bool = True
    return_window_days: int = 30
