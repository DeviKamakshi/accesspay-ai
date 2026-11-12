from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.saved import SavedItem, SavedSearch, SearchHistoryEntry
from app.services.ai_service import ai_service
from app.services.product_service import product_service
from app.services.saved_service import saved_service

router = APIRouter(prefix="/saved", tags=["Saved"])


class SaveItemRequest(BaseModel):
    product_id: str
    product_snapshot: Optional[Dict[str, Any]] = None


class SaveSearchRequest(BaseModel):
    original_query: Optional[str] = None
    display_query: Optional[str] = None
    structured_intent: Optional[Dict[str, Any]] = None
    filters: Optional[Dict[str, Any]] = None
    sort: Optional[str] = None
    reference_product_ids: Optional[List[str]] = None


@router.get("/items", response_model=List[SavedItem], summary="List saved items", description="Retrieve all products saved by the user for later review or purchase.")
def get_saved_items():
    return saved_service.list_saved_items()


@router.post("/items", response_model=SavedItem, summary="Save a product item", description="Save a product from the catalog or active search session to the user's Saved Items list.")
def save_item(req: SaveItemRequest):
    product = product_service.get_product_by_id(req.product_id)
    if product is not None:
        return saved_service.save_item(product)

    # Check active search session cache in case product came from live results
    session = ai_service.mock_service.session
    in_session = next(
        (
            p for p in (session.displayed_products + session.candidate_products)
            if p.get("id") == req.product_id
        ),
        None,
    )
    if in_session:
        return saved_service.save_item(in_session)
    if req.product_snapshot and req.product_snapshot.get("id") == req.product_id:
        return saved_service.save_item(req.product_snapshot)
    raise HTTPException(status_code=404, detail="Product not found to save.")


@router.delete("/items/{saved_item_id}", summary="Delete a saved item", description="Remove a product from the user's Saved Items list by saved item ID.")
def delete_saved_item(saved_item_id: str):
    removed = saved_service.remove_saved_item(saved_item_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Saved item not found.")
    return {"success": True, "removed_id": saved_item_id}


@router.post("/items/{saved_item_id}/add-to-cart", summary="Add saved item to cart", description="Add a previously saved product directly into the active shopping cart.")
async def add_saved_item_to_cart(saved_item_id: str):
    try:
        return await saved_service.add_saved_item_to_cart(saved_item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/searches", response_model=List[SavedSearch], summary="List saved searches", description="Retrieve all saved product search queries and their associated filters.")
def get_saved_searches():
    return saved_service.list_saved_searches()


@router.post("/searches", response_model=SavedSearch, summary="Save current or specified search", description="Save the active search session or a specified query and filters as a reusable Saved Search.")
def save_current_search(req: Optional[SaveSearchRequest] = None):
    session = ai_service.mock_service.session
    orig_q = (req.original_query if req and req.original_query else None) or session.original_query
    if not orig_q:
        raise HTTPException(status_code=400, detail="No active search to save.")
    disp_q = (req.display_query if req and req.display_query else None) or session.display_query or orig_q
    intent_dict = (
        req.structured_intent
        if req and req.structured_intent
        else (session.structured_search_intent.model_dump() if session.structured_search_intent else {})
    )
    filters_dict = (req.filters if req and req.filters is not None else session.filters) or {}
    sort_pref = (req.sort if req and req.sort is not None else session.sort)
    ref_ids = (
        req.reference_product_ids
        if req and req.reference_product_ids is not None
        else [p.get("id") for p in session.displayed_products if p.get("id")]
    )
    return saved_service.save_search(
        original_query=orig_q,
        display_query=disp_q,
        structured_intent=intent_dict,
        filters=filters_dict,
        sort=sort_pref,
        reference_product_ids=ref_ids,
    )


@router.delete("/searches/{saved_search_id}", summary="Delete a saved search", description="Remove a saved search entry by its saved search ID.")
def delete_saved_search(saved_search_id: str):
    removed = saved_service.delete_saved_search(saved_search_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Saved search not found.")
    return {"success": True, "removed_id": saved_search_id}


@router.post("/searches/{saved_search_id}/run", summary="Re-run a saved search", description="Execute a saved search query with its stored filters and update the active search session.")
async def run_saved_search(saved_search_id: str):
    try:
        return await ai_service.mock_service.run_saved_search_by_id(saved_search_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/history", response_model=List[SearchHistoryEntry], summary="List recent search history", description="Retrieve the most recent product search history entries.")
def get_search_history(limit: int = 20):
    return saved_service.list_search_history(limit=limit)


@router.post("/history/{history_id}/run", summary="Re-run a recent search", description="Re-execute a previous search from recent search history and update the active search session.")
async def run_search_history(history_id: str):
    try:
        return await ai_service.mock_service.run_search_history_by_id(history_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/history/{history_id}/save", response_model=SavedSearch, summary="Promote recent search to saved search", description="Save an entry from recent search history as a persistent Saved Search.")
def save_search_history_entry(history_id: str):
    try:
        return saved_service.save_history_entry_as_saved_search(history_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/history", summary="Clear recent search history", description="Delete all entries from the recent search history list.")
def clear_search_history():
    saved_service.clear_search_history()
    return {"success": True}

