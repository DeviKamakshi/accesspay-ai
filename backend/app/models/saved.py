from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class SavedItem(BaseModel):
    saved_item_id: str
    product_id: str
    product_title: str
    merchant: str
    price_at_save: float
    image_url: Optional[str] = None
    product_url: Optional[str] = None
    important_attributes: List[str] = Field(default_factory=list)
    product_snapshot: Dict[str, Any] = Field(default_factory=dict)
    saved_at: str


class SavedSearch(BaseModel):
    saved_search_id: str
    original_query: str
    display_query: str
    structured_intent: Dict[str, Any] = Field(default_factory=dict)
    filters: Dict[str, Any] = Field(default_factory=dict)
    sort: Optional[str] = None
    reference_product_ids: List[str] = Field(default_factory=list)
    saved_at: str


class SearchHistoryEntry(BaseModel):
    history_id: str
    search_id: str
    query: str
    display_query: str
    result_count: int = 0
    structured_intent: Dict[str, Any] = Field(default_factory=dict)
    filters: Dict[str, Any] = Field(default_factory=dict)
    sort: Optional[str] = None
    searched_at: str

