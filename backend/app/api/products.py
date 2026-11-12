from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from app.models.product import Product, ProductSearchQuery, ProductComparisonRequest
from app.services.product_service import product_service
from app.services.ai_service import ai_service
from app.services.shopping_session import extract_search_intent_rules

router = APIRouter(prefix="/products", tags=["Products"])


class ProductModeRequest(BaseModel):
    provider: str  # 'channel3', 'mock', or 'auto'


@router.get("", response_model=List[Product], summary="List cached catalog products", description="Return all products currently available in the local product catalog cache.")
def list_products():
    return product_service.get_all_products()


@router.get("/mode", summary="Get product provider mode", description="Return the active product search provider mode (channel3, mock, or auto).")
def get_product_mode():
    return product_service.get_mode_status()


@router.post("/mode", summary="Set product provider mode", description="Switch the active product search provider between channel3, mock, and auto.")
def set_product_mode(req: ProductModeRequest):
    provider = req.provider.lower().strip()
    if provider not in ["channel3", "mock", "auto"]:
        raise HTTPException(status_code=400, detail="Provider must be 'channel3', 'mock', or 'auto'")
    product_service.set_provider_mode(None if provider == "auto" else provider)
    return product_service.get_mode_status()


@router.get("/active-search")
def get_active_search():
    """Returns the single authoritative active search session snapshot synchronized with frontend cards."""
    sess = ai_service.mock_service.session
    displayed = list(getattr(sess, "displayed_products", []) or [])
    displayed_ids = [p.get("id") for p in displayed if isinstance(p, dict) and p.get("id")]
    return {
        "search_id": getattr(sess, "search_id", None),
        "search_generation": getattr(sess, "search_generation", 0),
        "original_query": getattr(sess, "original_query", None) or getattr(sess, "last_query", ""),
        "display_query": getattr(sess, "display_query", None) or getattr(sess, "last_query", ""),
        "displayed_products": displayed,
        "displayed_product_ids": displayed_ids,
        "count": len(displayed),
        "has_more": bool(getattr(sess, "has_more", False)),
        "total_available": int(getattr(sess, "total_available", len(displayed))),
        "filters": getattr(sess, "filters", {}) or {},
        "sort": getattr(sess, "sort", None),
    }


@router.get("/suggestions")
def get_search_suggestions(q: str = "", limit: int = 6):
    """Lightweight, non-Channel3 query suggestions derived from history, saved items, and catalog cache."""
    return {
        "query": q,
        "suggestions": product_service.get_search_suggestions(q, limit=limit),
    }


@router.get("/{product_id}", response_model=Product, summary="Get product details by ID", description="Retrieve full details for a single product by its product ID.")
def get_product(product_id: str):
    product = product_service.get_product_by_id(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post(
    "/search",
    summary="Search for products using the configured commerce provider",
    description=(
        "Searches physical products using the configured commerce provider (Channel3 in this hackathon prototype; "
        "future deployments may plug in merchant-owned catalogs). Synchronizes the active shopping session."
    ),
)
async def search_products(query: ProductSearchQuery):
    need = query.accessibility_needs[0] if query.accessibility_needs else None
    intent = extract_search_intent_rules(query.query, last_intent=None)
    if query.budget_limit is not None:
        intent.max_price = query.budget_limit
    if query.min_price is not None:
        intent.min_price = query.min_price
    if query.requirements:
        for req in query.requirements:
            req_clean = req.strip().lower()
            if req_clean and req_clean not in intent.features:
                intent.features.append(req_clean)

    res = await product_service.search_products(
        query=query.query,
        budget_limit=query.budget_limit,
        min_price=query.min_price,
        accessibility_need=need,
        requirements=query.requirements,
        intent=intent,
    )
    meta = ai_service.mock_service.sync_external_search_results(
        query=query.query,
        intent=intent,
        search_res=res,
    )
    res.update(meta)
    res["displayed_product_ids"] = [
        p.id if hasattr(p, "id") else p.get("id")
        for p in res.get("products", [])
    ]
    return res


@router.post("/show-more")
async def show_more_products():
    """Appends the next batch of candidates for the current ActiveSearchSession."""
    return await ai_service.mock_service.show_more_results()


@router.post("/compare", summary="Compare selected products side-by-side", description="Compare two or more selected products across price, rating, merchant, and key attributes.")
def compare_products(req: ProductComparisonRequest):
    return product_service.compare_products(req.product_ids)
