from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any
from app.models.analytics import AccessibilityActivitySummary
from app.services.analytics_service import analytics_service
from app.db.database import db

router = APIRouter(prefix="/analytics", tags=["System"])


class GridQueryRequest(BaseModel):
    query: str


@router.get("/summary", response_model=AccessibilityActivitySummary, summary="Get accessibility activity summary", description="Retrieve summary metrics for voice and accessibility interactions.")
def get_accessibility_activity_summary():
    return analytics_service.get_accessibility_summary()


@router.post("/grid-query", summary="Query purchase analytics grid", description="Translate a natural-language query into structured purchase analytics results.")
def query_grid(req: GridQueryRequest):
    return analytics_service.query_purchase_analytics(req.query)


@router.get("/audit-events", summary="List recent audit events", description="Retrieve the most recent security and confirmation audit log events.")
def get_audit_events():
    return {
        "events": db.get_recent_audit_events(limit=50)
    }
