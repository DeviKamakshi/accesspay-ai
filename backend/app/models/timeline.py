from pydantic import BaseModel
from typing import Optional


class TimelineEvent(BaseModel):
    id: str
    date: str  # YYYY-MM-DD
    display_date: str  # e.g., "NOV 4", "NOV 8"
    title: str
    category: str  # 'purchase', 'delivery', 'subscription', 'trial_expiration'
    amount: Optional[float] = None
    merchant: Optional[str] = None
    description: str
    status: str  # 'COMPLETED', 'SCHEDULED', 'UPCOMING', 'ACTIVE'
    is_recurring: bool = False
    recurring_interval: Optional[str] = None
    highlight: bool = False
