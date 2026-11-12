from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.db.database import db
from app.db.seed_data import ensure_database_seeded
from app.models.analytics import OrderRecord, OrderLineItem
from app.services.ai_service import ai_service
from app.services.cart_service import cart_service
from app.services.confirmation_service import confirmation_service, PurchaseState
from app.services.product_service import product_service


def _mock_channel3_guard():
    async def post(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = []
        return resp

    client = MagicMock()
    client.post = AsyncMock(side_effect=post)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, client


@pytest.fixture(autouse=True)
def clean_voice_first_state():
    orig_gemini = ai_service.llm_service.gemini_key
    orig_openai = ai_service.llm_service.openai_key
    ai_service.llm_service.gemini_key = ""
    ai_service.llm_service.openai_key = ""
    db.clear_all()
    ensure_database_seeded()
    cart_service.clear()
    confirmation_service.reset()
    ai_service.reset_conversation()
    yield
    cart_service.clear()
    confirmation_service.reset()
    ai_service.reset_conversation()
    db.clear_all()
    ensure_database_seeded()
    ai_service.llm_service.gemini_key = orig_gemini
    ai_service.llm_service.openai_key = orig_openai


def test_generic_search_suggestions_no_channel3_calls():
    client = TestClient(app)
    saved = client.post("/api/saved/searches", json={"original_query": "stainless steel water bottle"})
    assert saved.status_code == 200

    mock_ctx, mock_client = _mock_channel3_guard()
    with patch("httpx.AsyncClient", return_value=mock_ctx):
        short_res = client.get("/api/products/suggestions?q=w")
        assert short_res.status_code == 200
        assert short_res.json()["suggestions"] == []

        res = client.get("/api/products/suggestions?q=bottle&limit=6")
        assert res.status_code == 200
        payload = res.json()
        assert 1 <= len(payload["suggestions"]) <= 6
        assert any("bottle" in s.lower() for s in payload["suggestions"])
        assert mock_client.post.call_count == 0


def test_view_scoped_ordinal_resolution_and_saved_item_checkout():
    client = TestClient(app)
    products = product_service.get_all_products()
    assert len(products) >= 3
    p1, p2 = products[0], products[1]

    s1 = client.post("/api/saved/items", json={"product_id": p1.id}).json()["saved_item_id"]
    s2 = client.post("/api/saved/items", json={"product_id": p2.id}).json()["saved_item_id"]

    mock_ctx, mock_client = _mock_channel3_guard()
    with patch("httpx.AsyncClient", return_value=mock_ctx):
        # On SAVED_ITEMS, "Open the second one" must resolve saved item #2 without calling Channel3
        r_open = client.post(
            "/api/ai/intent",
            json={
                "message": "Open the second one",
                "input_mode": "voice",
                "current_view": "SAVED_ITEMS",
                "visible_saved_item_ids": [s1, s2],
            },
        ).json()
        assert r_open["action"] == "OPEN_SAVED_ITEM"
        assert r_open["saved_item_id"] == s2
        assert r_open["channel3_called"] is False

        # On SAVED_ITEMS with selected_saved_item_id, "Proceed to checkout" adds item & builds review
        r_chk = client.post(
            "/api/ai/intent",
            json={
                "message": "Proceed to checkout",
                "input_mode": "voice",
                "current_view": "SAVED_ITEMS",
                "visible_saved_item_ids": [s1, s2],
                "selected_saved_item_id": s2,
            },
        ).json()
        assert r_chk["action"] == "PAYMENT_REVIEW_READY"
        assert r_chk["review"]["cart"]["item_count"] >= 1
        assert r_chk["channel3_called"] is False


def test_previous_order_empty_and_populated_details_and_reorder():
    client = TestClient(app)
    mock_ctx, mock_client = _mock_channel3_guard()

    # Empty order history behavior
    with db.get_connection() as conn:
        conn.execute("DELETE FROM orders")
        conn.commit()
    with patch("httpx.AsyncClient", return_value=mock_ctx):
        r_empty = client.post(
            "/api/ai/intent",
            json={"message": "Go to previous order", "input_mode": "voice", "current_view": "SHOP"},
        ).json()
        assert r_empty["action"] == "OPEN_ORDER"
        assert r_empty["order"] is None
        assert r_empty["message"] == "You don't have any completed orders yet."
        assert r_empty["channel3_called"] is False

    # Seed two completed orders (save older then latest so latest is newest)
    products = product_service.get_all_products()
    p1, p2 = products[0], products[1]
    older = OrderRecord(
        order_id="ord_older_1",
        date="2026-11-10",
        product_id=p1.id,
        product_title=p1.title,
        merchant=p1.merchant,
        category=p1.category,
        item_price=p1.price,
        amount=p1.price,
        subtotal=p1.price,
        shipping=4.5,
        tax=2.1,
        total=round(p1.price + 6.6, 2),
        items=[
            OrderLineItem(
                product_id=p1.id,
                product_title=p1.title,
                merchant=p1.merchant,
                category=p1.category,
                unit_price=p1.price,
                quantity=1,
                line_total=p1.price,
            )
        ],
        payment_status="Completed (Sandbox)",
    )
    latest = OrderRecord(
        order_id="ord_latest_2",
        date="2026-11-11",
        product_id=p2.id,
        product_title=p2.title,
        merchant=p2.merchant,
        category=p2.category,
        item_price=p2.price,
        amount=p2.price,
        subtotal=p2.price,
        shipping=5.25,
        tax=3.4,
        total=round(p2.price + 8.65, 2),
        items=[
            OrderLineItem(
                product_id=p2.id,
                product_title=p2.title,
                merchant=p2.merchant,
                category=p2.category,
                unit_price=p2.price,
                quantity=1,
                line_total=p2.price,
            )
        ],
        payment_status="Completed (Sandbox)",
    )
    db.save_order(older.model_dump())
    db.save_order(latest.model_dump())

    with patch("httpx.AsyncClient", return_value=mock_ctx):
        r_prev = client.post(
            "/api/ai/intent",
            json={"message": "Go to previous order", "input_mode": "voice", "current_view": "SHOP"},
        ).json()
        assert r_prev["action"] == "OPEN_ORDER"
        assert r_prev["order_id"] == "ord_latest_2"
        assert r_prev["channel3_called"] is False

        # Open second order on ORDERS view
        r_second = client.post(
            "/api/ai/intent",
            json={
                "message": "Open the second one",
                "input_mode": "voice",
                "current_view": "ORDERS",
                "visible_order_ids": ["ord_latest_2", "ord_older_1"],
            },
        ).json()
        assert r_second["action"] == "OPEN_ORDER"
        assert r_second["order_id"] == "ord_older_1"

        # Order detail queries use selected_order_id and never call Channel3
        r_ship = client.post(
            "/api/ai/intent",
            json={
                "message": "How much was shipping?",
                "input_mode": "voice",
                "current_view": "ORDER_DETAILS",
                "selected_order_id": "ord_latest_2",
            },
        ).json()
        assert r_ship["action"] == "ORDER_DETAILS"
        assert "5.25" in r_ship["message"]

        r_tax = client.post(
            "/api/ai/intent",
            json={
                "message": "How much tax?",
                "input_mode": "voice",
                "current_view": "ORDER_DETAILS",
                "selected_order_id": "ord_latest_2",
            },
        ).json()
        assert r_tax["action"] == "ORDER_DETAILS"
        assert "3.40" in r_tax["message"]

        # Reorder rebuilds Cart + Review safely without charging
        r_re = client.post(
            "/api/ai/intent",
            json={
                "message": "Buy this again",
                "input_mode": "voice",
                "current_view": "ORDER_DETAILS",
                "selected_order_id": "ord_older_1",
            },
        ).json()
        assert r_re["action"] == "PAYMENT_REVIEW_READY"
        assert r_re["review"]["cart"]["items"][0]["product_id"] == p1.id
        assert confirmation_service.get_state() == PurchaseState.PAYMENT_REVIEW


def test_cart_voice_mutations_and_strict_confirmation_guard():
    client = TestClient(app)
    products = product_service.get_all_products()
    p1, p2 = products[0], products[1]
    cart_service.add_item(p1.id, quantity=1)
    cart_service.add_item(p2.id, quantity=1)

    mock_ctx, mock_client = _mock_channel3_guard()
    with patch("httpx.AsyncClient", return_value=mock_ctx):
        # Ordinal remove from cart
        r_rem = client.post(
            "/api/ai/intent",
            json={
                "message": "Remove the second item",
                "input_mode": "voice",
                "current_view": "CART",
                "visible_cart_product_ids": [p1.id, p2.id],
            },
        ).json()
        assert r_rem["action"] == "CART_UPDATED"
        assert len(r_rem["cart"]["items"]) == 1
        assert r_rem["cart"]["items"][0]["product_id"] == p1.id

        # Quantity change on CART
        r_qty = client.post(
            "/api/ai/intent",
            json={
                "message": "Change quantity to 3",
                "input_mode": "voice",
                "current_view": "CART",
                "visible_cart_product_ids": [p1.id],
            },
        ).json()
        assert r_qty["cart"]["items"][0]["quantity"] == 3

        # Review -> Confirmation -> Casual confirmation REJECTED -> Exact phrase ACCEPTED
        r_rev = client.post(
            "/api/ai/intent",
            json={"message": "Checkout", "input_mode": "voice", "current_view": "CART"},
        ).json()
        assert r_rev["action"] == "PAYMENT_REVIEW_READY"
        expected_phrase = r_rev["review"]["expected_phrase"]

        for casual in ("Yes", "Okay", "Continue", "Go ahead"):
            r_bad = client.post(
                "/api/ai/intent",
                json={
                    "message": casual,
                    "input_mode": "voice",
                    "current_view": "CONFIRMATION_REQUIRED",
                },
            ).json()
            assert r_bad["action"] == "AMBIGUITY_GUARD"
            assert confirmation_service.get_state() in (
                PurchaseState.PAYMENT_REVIEW,
                PurchaseState.CONFIRMATION_REQUIRED,
            )

        r_ok = client.post(
            "/api/ai/intent",
            json={
                "message": expected_phrase,
                "input_mode": "voice",
                "current_view": "CONFIRMATION_REQUIRED",
            },
        ).json()
        assert r_ok["action"] == "PAYMENT_CONFIRMED"
        assert r_ok["success"] is True
        assert mock_client.post.call_count == 0
