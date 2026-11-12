from fastapi import APIRouter
from typing import Dict, Any
from app.models.accessibility import AccessibilityPreferences, ModeSwitchRequest
from app.services.accessibility_service import accessibility_service

router = APIRouter(prefix="/accessibility", tags=["System"])


@router.get("/preferences", response_model=AccessibilityPreferences, summary="Get accessibility preferences", description="Retrieve the current accessibility preferences for the active session.")
def get_preferences():
    return accessibility_service.get_preferences()


@router.put("/preferences", response_model=AccessibilityPreferences, summary="Update accessibility preferences", description="Update one or more accessibility preference fields for the active session.")
def update_preferences(updates: Dict[str, Any]):
    return accessibility_service.update_preferences(updates)


@router.post("/mode", response_model=AccessibilityPreferences, summary="Set accessibility mode", description="Switch the active accessibility mode preference.")
def switch_mode(req: ModeSwitchRequest):
    return accessibility_service.set_mode(req.mode)


@router.post("/reset", response_model=AccessibilityPreferences, summary="Reset accessibility preferences", description="Reset all accessibility preferences back to their default values.")
def reset_preferences():
    accessibility_service.reset_to_defaults()
    return accessibility_service.get_preferences()
