from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SubscriptionOffer(BaseModel):
    id: str
    provider: str
    name: str
    description: str
    image_url: Optional[str] = None
    currency: str = "USD"
    amount_due_today: float
    recurring_amount: float
    billing_frequency: str  # e.g. "monthly", "yearly"
    billing_interval: str   # PayPal interval_unit: "MONTH", "YEAR", "WEEK"
    interval_count: int = 1
    trial_period: Optional[str] = None
    setup_fee: Optional[float] = None
    renewal_behavior: str
    cancellation_information: str
    paypal_product_id: Optional[str] = None
    paypal_plan_id: Optional[str] = None
    source: str = "demo_subscription_catalog"
    is_demo: bool = True


class SubscriptionReviewRequest(BaseModel):
    offer_id: str


class SubscriptionReview(BaseModel):
    review_token: str
    offer: SubscriptionOffer
    due_today: float
    recurring_amount: float
    billing_frequency: str
    expected_phrase: str
    is_invalidated: bool = False
    invalidation_reason: Optional[str] = None
    confirmation_granted: bool = False


class SubscriptionConfirmRequest(BaseModel):
    review_token: str
    spoken_phrase: str
    method: str = "VOICE"


class SubscriptionConfirmResponse(BaseModel):
    success: bool
    is_ambiguous: bool = False
    wrong_amount: bool = False
    wrong_frequency: bool = False
    message: str
    review_token: str
    expected_phrase: str


class PayPalSubscriptionCreateRequest(BaseModel):
    review_token: str
    return_url: Optional[str] = None
    cancel_url: Optional[str] = None


class SubscriptionRecord(BaseModel):
    subscription_id: str
    offer_id: str
    plan_name: str
    provider: str
    currency: str = "USD"
    amount_due_today: float
    recurring_amount: float
    billing_frequency: str
    paypal_product_id: Optional[str] = None
    paypal_plan_id: Optional[str] = None
    paypal_subscription_id: str
    status: str  # APPROVAL_PENDING, ACTIVE, CANCELLED
    approval_url: Optional[str] = None
    created_at: str
    updated_at: str
    cancelled_at: Optional[str] = None
    is_demo_catalog: bool = True
    paypal_environment: str = "sandbox"


class SubscriptionCancelRequest(BaseModel):
    confirmation_phrase: str
    reason: Optional[str] = None

