from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from app.models.analytics import OrderRecord
from app.services.order_service import order_service

router = APIRouter(prefix="/orders", tags=["Orders"])


class ReturnRequest(BaseModel):
    product_name: str = "headphones"


@router.get("", response_model=List[OrderRecord], summary="List completed one-time orders", description="Retrieve all completed one-time orders from the local store.")
def get_orders():
    return order_service.get_all_orders()


@router.get("/track", summary="Track recent order status", description="Look up tracking and fulfillment status for a recent order by optional query.")
def track_order(query: Optional[str] = None):
    return order_service.track_order(query)


@router.post("/return", summary="Check return eligibility for an order", description="Evaluate return eligibility and instructions for a previously purchased item.")
def return_assistant(req: ReturnRequest):
    return order_service.return_assistant(req.product_name)


@router.post("/reorder-last", summary="Prepare purchase review for the most recent order", description="Load the most recent completed order into the cart and prepare a fresh purchase review.")
async def reorder_last_order():
    try:
        return await order_service.reorder_order(None)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{order_id}", response_model=OrderRecord, summary="Retrieve order details by ID", description="Fetch full details for a single completed order by its order ID.")
def get_order_details(order_id: str):
    order = order_service.get_order_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.post("/{order_id}/reorder", summary="Prepare purchase review to reorder a specific order", description="Load items from a specific past order into the cart and prepare a fresh purchase review.")
async def reorder_specific_order(order_id: str):
    try:
        return await order_service.reorder_order(order_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
