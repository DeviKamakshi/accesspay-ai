from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from app.services.ai_service import ai_service
from app.services.voice_service import voice_service

router = APIRouter(prefix="/ai", tags=["AI & Intent"])


class UserIntentRequest(BaseModel):
    message: str = Field(
        ...,
        description="Natural-language shopping or navigation command from voice or text.",
        json_schema_extra={"examples": ["Find wireless headphones under $80", "Compare the first two"]},
    )
    input_mode: str = Field(default="text", description="Input channel: 'text', 'voice', or 'chip'.")
    active_search_id: Optional[str] = Field(default=None, description="Active search session identifier for contextual follow-ups.")
    search_generation: Optional[int] = Field(default=None, description="Monotonic search generation counter to discard stale turns.")
    visible_product_ids: Optional[List[str]] = Field(default=None, description="IDs of products currently displayed to the user.")
    raw_transcript: Optional[str] = Field(default=None, description="Raw speech-to-text transcript prior to normalization.")
    current_view: Optional[str] = Field(default=None, description="Current UI view name (e.g., SHOP, CART, ORDERS).")
    visible_saved_item_ids: Optional[List[str]] = None
    visible_saved_search_ids: Optional[List[str]] = None
    visible_order_ids: Optional[List[str]] = None
    selected_order_id: Optional[str] = None
    selected_saved_item_id: Optional[str] = None
    visible_cart_product_ids: Optional[List[str]] = None


class IntentResponse(BaseModel):
    action: str = Field(..., description="Resolved application action (e.g., SEARCH_RESULTS, COMPARE, PAYMENT_REVIEW_READY).")
    speech_response: Optional[str] = Field(default=None, description="Accessible spoken/display summary of the result.")
    message: Optional[str] = None
    search_id: Optional[str] = None
    search_generation: Optional[int] = None
    products: Optional[List[Dict[str, Any]]] = None

    model_config = {"extra": "allow"}


@router.post(
    "/intent",
    response_model=IntentResponse,
    summary="Interpret a conversational shopping command",
    description=(
        "Routes natural-language shopping, comparison, cart, saved-item, and checkout-navigation commands. "
        "May invoke Google Gemini for NLU and Channel3 for product discovery. "
        "Gemini never supplies authoritative prices, cart totals, or payment authorization."
    ),
)
async def process_intent(req: UserIntentRequest):
    return await ai_service.process_user_intent(
        req.message,
        input_mode=req.input_mode,
        active_search_id=req.active_search_id,
        search_generation=req.search_generation,
        visible_product_ids=req.visible_product_ids,
        raw_transcript=req.raw_transcript,
        context_data={
            "current_view": req.current_view,
            "visible_saved_item_ids": req.visible_saved_item_ids,
            "visible_saved_search_ids": req.visible_saved_search_ids,
            "visible_order_ids": req.visible_order_ids,
            "selected_order_id": req.selected_order_id,
            "selected_saved_item_id": req.selected_saved_item_id,
            "visible_cart_product_ids": req.visible_cart_product_ids,
        },
    )


@router.get("/commands", summary="List suggested voice commands", description="Return suggested voice commands tailored to the active shopping context.")
def get_suggested_commands():
    return {
        "commands": voice_service.get_suggested_commands()
    }


@router.get("/status", summary="Get AI provider readiness status", description="Return configuration and availability status for the conversational AI provider.")
def get_ai_status():
    return ai_service.get_status()


@router.post("/reset-conversation", summary="Reset conversational AI context", description="Clear the active conversational AI history and shopping intent context.")
def reset_ai_conversation():
    ai_service.reset_conversation()
    return {"status": "ok", "message": "AI conversation context reset"}
