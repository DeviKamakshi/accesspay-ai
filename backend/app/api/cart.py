from fastapi import APIRouter
from app.models.cart import Cart, AddToCartRequest, UpdateCartItemRequest
from app.services.cart_service import cart_service

router = APIRouter(prefix="/cart", tags=["Cart"])


@router.get("", response_model=Cart, summary="Retrieve the current cart", description="Returns all cart items with server-computed subtotal, shipping, tax, and total.")
def get_cart():
    return cart_service.get_cart()


@router.post("/items", response_model=Cart, summary="Add an item to the cart", description="Adds a verified product to the cart and recalculates server-authoritative totals.")
def add_to_cart(req: AddToCartRequest):
    return cart_service.add_item(
        product_id=req.product_id,
        quantity=req.quantity,
        variant=req.selected_variant
    )


@router.put("/items/{product_id}", response_model=Cart, summary="Update cart item quantity", description="Update the quantity of an item currently in the active shopping cart.")
def update_item_quantity(product_id: str, req: UpdateCartItemRequest):
    return cart_service.update_quantity(product_id=product_id, quantity=req.quantity)


@router.delete("/items/{product_id}", response_model=Cart, summary="Remove an item from the cart", description="Remove a matching item from the active shopping cart by product ID or title.")
def remove_from_cart(product_id: str):
    return cart_service.remove_item(product_id)


@router.delete("", response_model=Cart, summary="Clear all items from the cart", description="Remove all items from the active shopping cart.")
def clear_cart():
    return cart_service.clear()
