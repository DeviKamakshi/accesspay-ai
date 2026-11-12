from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from app.models.cart import Cart
from app.models.analytics import OrderLineItem


class PurchaseState(str, Enum):
    BROWSING = "BROWSING"
    PRODUCT_SELECTED = "PRODUCT_SELECTED"
    CART = "CART"
    PAYMENT_REVIEW = "PAYMENT_REVIEW"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    PAYMENT_PROCESSING = "PAYMENT_PROCESSING"
    PAYMENT_COMPLETE = "PAYMENT_COMPLETE"
    CANCELLED = "CANCELLED"
    PAYMENT_FAILED = "PAYMENT_FAILED"


class ConfirmationEvent(BaseModel):
    timestamp: str
    event_type: str  # e.g., 'REVIEW_DISPLAYED', 'CONFIRMATION_REQUESTED', 'AMBIGUOUS_REJECTED', 'EXACT_MATCH_ACCEPTED', 'PAYMENT_SUBMITTED', 'PAYMENT_CAPTURED', 'CANCELLED'
    details: str
    interaction_mode: str = "VOICE"


class PurchaseReview(BaseModel):
    state: PurchaseState = PurchaseState.PAYMENT_REVIEW
    cart: Cart
    
    # Financial breakdown
    item_subtotal: float
    shipping: float
    tax: float
    discount: float = 0.0
    total_today: float
    future_payments: str = "None"
    
    # Adaptive confirmation rules
    is_high_value: bool = False
    high_value_step: int = 1
    high_value_total_steps: int = 1
    requires_exact_phrase: bool = True
    expected_phrase: str  # e.g., "Confirm $59.36 purchase"
    
    # Guardians
    is_subscription: bool = False
    subscription_terms: Optional[str] = None
    subscription_acknowledged: bool = False
    
    is_free_trial: bool = False
    trial_terms: Optional[str] = None
    trial_acknowledged: bool = False
    
    quantity_warning: Optional[str] = None
    shipping_warning: Optional[str] = None
    
    # Price & Total-change protection snapshots
    snapshot_total: float
    snapshot_shipping: float
    snapshot_item_subtotal: float
    snapshot_tax: float = 0.0
    snapshot_quantity: int = 1
    snapshot_variant: str = ""
    snapshot_items: str = ""
    snapshot_recurring_terms: str = "None"
    
    # Security & audit token
    review_token: str
    is_invalidated: bool = False
    invalidation_reason: Optional[str] = None


class ConfirmPurchaseRequest(BaseModel):
    review_token: str
    spoken_phrase: Optional[str] = None
    confirmation_method: str = "VOICE"  # 'VOICE', 'LARGE_CONTROLS', 'KEYBOARD', 'SWITCH', 'BUTTON_CLICK'
    subscription_acknowledged: Optional[bool] = None
    trial_acknowledged: Optional[bool] = None
    high_value_step: Optional[int] = None
    authorize_only: bool = False


class PurchaseResponse(BaseModel):
    success: bool
    state: PurchaseState
    message: str
    order_id: Optional[str] = None
    paypal_order_id: Optional[str] = None
    paypal_capture_id: Optional[str] = None
    product_title: Optional[str] = None
    merchant: Optional[str] = None
    is_subscription: Optional[bool] = None
    amount_charged: Optional[float] = None
    item_subtotal: Optional[float] = None
    shipping: Optional[float] = None
    tax: Optional[float] = None
    items: List[OrderLineItem] = Field(default_factory=list)
    requires_step: Optional[int] = None
    is_ambiguous: bool = False
    events: List[ConfirmationEvent] = Field(default_factory=list)
