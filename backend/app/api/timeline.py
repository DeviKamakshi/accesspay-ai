from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from app.models.timeline import TimelineEvent
from app.services.timeline_service import timeline_service

router = APIRouter(prefix="/timeline", tags=["System"])


class TimelineQueryRequest(BaseModel):
    query: str


@router.get("", response_model=List[TimelineEvent], summary="List commerce timeline events", description="Retrieve all upcoming and recent commerce timeline events for the active session.")
def get_timeline():
    return timeline_service.get_all_timeline_events()


@router.post("/query", summary="Query commerce timeline", description="Filter or query commerce timeline events using natural language.")
def query_timeline(req: TimelineQueryRequest):
    return timeline_service.query_timeline(req.query)
