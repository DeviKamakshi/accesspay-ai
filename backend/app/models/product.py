from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Dict, Any


class Product(BaseModel):
    id: str
    title: str
    name: Optional[str] = None
    description: str = ""
    price: float
    original_price: Optional[float] = None
    shipping: float = 0.0
    estimated_tax: float = 0.0
    category: str = "General"
    merchant: str = "Online Retailer"
    image_url: str = ""
    image_alt: Optional[str] = None
    product_url: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    is_available: bool = True
    availability: Optional[str] = "InStock"
    attributes: Dict[str, Any] = Field(default_factory=dict)
    source: str = "mock"  # 'channel3' or 'mock'

    # Subscription / Recurring logic
    is_subscription: bool = False
    subscription_period: Optional[str] = None  # e.g., 'month', 'year'
    is_trial: bool = False
    trial_days: int = 0
    trial_post_price: float = 0.0

    # Accessibility & product features (only from actual returned data)
    documented_accessibility_features: List[str] = Field(default_factory=list)
    ai_inferred_accessibility: List[str] = Field(default_factory=list)

    # Ranking explanation
    ranking_badge: Optional[str] = None  # 'BEST MATCH', 'BEST VALUE', 'LOWEST PRICE'
    ranking_reason: Optional[str] = None

    # Cheaper alternative relations
    cheaper_alternative_id: Optional[str] = None
    savings_amount: Optional[float] = None

    # Variants (color, size, model)
    variants: Optional[Dict[str, List[str]]] = None

    @model_validator(mode="after")
    def sync_name_and_alt(self) -> "Product":
        if not self.name:
            self.name = self.title
        if not self.image_alt:
            if self.merchant:
                self.image_alt = f"{self.title} from {self.merchant}"
            else:
                self.image_alt = self.title
        return self


class ProductSearchQuery(BaseModel):
    query: str
    budget_limit: Optional[float] = None
    min_price: Optional[float] = None
    category: Optional[str] = None
    requirements: List[str] = Field(default_factory=list)
    accessibility_needs: List[str] = Field(default_factory=list)
    merchant_preference: Optional[str] = None
    sort_by: Optional[str] = "relevance"


class ProductComparisonRequest(BaseModel):
    product_ids: List[str]
