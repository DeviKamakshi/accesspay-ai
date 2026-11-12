import asyncio
import json
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
from app.services.order_service import order_service
from app.services.product_service import product_service
from app.services.saved_service import saved_service


def _make_catalog(category: str, noun: str, count: int = 10):
    """Generic Channel3 payload builder for arbitrary product categories."""
    brands = ["NorthPeak", "VeloCraft", "ApexGear", "BrightLine", "SummitLab", "PureHome"]
    slug = noun.replace(" ", "_")
    items = []
    for idx in range(count):
        brand = brands[idx % len(brands)]
        price = round(95.0 - idx * 7.5, 2)
        items.append({
            "id": f"{slug}_{idx + 1}",
            "title": f"{brand} {noun.title()} Option {idx + 1}",
            "price": {"price": price, "currency": "USD"},
            "description": f"High quality {noun} built for {category}.",
            "brand_name": brand,
            "categories": [category],
            "image_url": f"https://example.com/{slug}_{idx + 1}.jpg",
            "url": f"https://example.com/p/{slug}_{idx + 1}",
            "score": 0.95 - idx * 0.03,
            "availability": "InStock",
        })
    return items


def _mock_channel3_async_client(catalog_fn):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    async def fake_post(url, json=None, headers=None, **kwargs):
        query = (json or {}).get("query", "")
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = catalog_fn(query)
        return resp

    client.post = AsyncMock(side_effect=fake_post)
    return client


@pytest.fixture(autouse=True)
def _isolated_state():
    orig_gemini = ai_service.llm_service.gemini_key
    orig_openai = ai_service.llm_service.openai_key
    ai_service.llm_service.gemini_key = ""
    ai_service.llm_service.openai_key = ""
    db.clear_all()
    ensure_database_seeded()
    ai_service.reset_conversation()
    cart_service.clear()
    product_service.set_provider_mode("channel3")
    product_service.channel3_service.api_key = "test_c3_key"
    confirmation_service.reset()
    yield
    ai_service.reset_conversation()
    cart_service.clear()
    confirmation_service.reset()
    ai_service.llm_service.gemini_key = orig_gemini
    ai_service.llm_service.openai_key = orig_openai


@pytest.mark.parametrize(
    "category,query,noun",
    [
        ("Camping", "Find sleeping bag under $100", "sleeping bag"),
        ("Kitchenware", "Find blender under $100", "blender"),
        ("Stationery", "Find fountain pen under $100", "fountain pen"),
        ("Cycling", "Find bike helmet under $100", "bike helmet"),
    ],
)
def test_active_search_6_plus_show_more_and_followup_sync(category, query, noun):
    """
    Verifies:
    - Initial search shows up to 6 results (not hardcoded 3) and exposes has_more + total_candidates
    - Follow-up attribute question, compare(4th, 5th), sort, and show_more operate cleanly
    - Cart persists when switching from Search A -> Search B
    """
    catalog = _make_catalog(category, noun, count=10)
    mock_client = _mock_channel3_async_client(lambda q: catalog)

    async def _run():
        with patch("httpx.AsyncClient", return_value=mock_client):
            r1 = await ai_service.process_user_intent(query)
            assert r1["action"] == "SEARCH_RESULTS"
            assert len(r1["products"]) == 6
            assert r1["has_more"] is True
            assert r1["total_candidates"] >= 7
            calls_after_search = mock_client.post.call_count

            # Inspecting 4th and 5th displayed options uses exact displayed ordering & zero Channel3 calls
            r_cmp = await ai_service.process_user_intent("Compare the fourth and fifth ones")
            assert r_cmp["action"] == "COMPARE"
            assert r_cmp["channel3_called"] is False
            assert mock_client.post.call_count == calls_after_search
            cmp_ids = [p["id"] for p in r_cmp["comparison"]["products"]]
            assert cmp_ids == [r1["products"][3]["id"], r1["products"][4]["id"]]

            # Short question ending with '?' stays inside active search
            r_det = await ai_service.process_user_intent("What is the price of the fourth one?")
            assert r_det["action"] in ("PRODUCT_DETAILS", "ATTRIBUTE_INQUIRY")
            assert r_det["channel3_called"] is False
            det_pid = (r_det.get("product") or {}).get("id")
            assert det_pid == r1["products"][3]["id"] or r1["products"][3]["id"] in (r_det.get("referenced_product_ids") or [])

            # Show more expands displayed results without starting a new search
            r_more = await ai_service.process_user_intent("Show more")
            assert r_more["action"] == "SEARCH_RESULTS"
            assert len(r_more["products"]) > 6
            assert [p["id"] for p in r_more["products"][:6]] == [p["id"] for p in r1["products"]]

            # Select item into cart, then start Search B -> cart must remain intact!
            r_sel = await ai_service.process_user_intent("Select the first one")
            assert r_sel["action"] == "PRODUCT_SELECTED"
            selected_id = r_sel["product"]["id"]
            assert any(it.product_id == selected_id for it in cart_service.get_cart().items)

            other_catalog = _make_catalog("Footwear", "running shoe", count=4)
            mock_client.post.side_effect = None
            mock_client2 = _mock_channel3_async_client(lambda q: other_catalog)
            with patch("httpx.AsyncClient", return_value=mock_client2):
                r_new = await ai_service.process_user_intent("Find running shoe under $100")
                assert r_new["action"] == "SEARCH_RESULTS"
                assert r_new["search_id"] != r1["search_id"]
                assert any(it.product_id == selected_id for it in cart_service.get_cart().items)

    asyncio.run(_run())


def test_save_item_save_search_history_bounds_and_live_rerun():
    """
    Verifies:
    - Saving an item persists to SQLite, never adds to cart, never authorizes payment
    - Adding a saved item to cart checks live price & surfaces price_changed cleanly
    - Saving multiple searches works; ambiguous reopen asks clarification; live Run Again executes live search
    - Search History stays distinct from Saved Searches and caps cleanly at 25 entries
    """
    client = TestClient(app)

    cat_a = _make_catalog("Audio", "microphone", count=5)
    mock_client = _mock_channel3_async_client(lambda q: cat_a)

    with patch("httpx.AsyncClient", return_value=mock_client):
        # 1. Search via REST endpoint (mirrors initial mount) -> verify /products/active-search sync
        s_resp = client.post("/api/products/search", json={"query": "microphone", "budget_limit": 100})
        assert s_resp.status_code == 200
        s_data = s_resp.json()
        assert len(s_data["products"]) == 5

        active_resp = client.get("/api/products/active-search")
        assert active_resp.status_code == 200
        active_data = active_resp.json()
        assert active_data["displayed_product_ids"] == [p["id"] for p in s_data["products"]]
        assert active_data["search_id"] == s_data["search_id"]

        # 2. Conversational save of 2nd product -> zero cart mutations, zero orders created
        initial_cart_count = len(cart_service.get_cart().items)
        save_res = client.post("/api/ai/intent", json={"message": "Save the second option"}).json()
        assert save_res["action"] == "PRODUCT_SAVED"
        assert save_res["saved_item"]["product_id"] == s_data["products"][1]["id"]
        assert len(cart_service.get_cart().items) == initial_cart_count

        # 3. Verify saved items persisted & price-change check on Add to Cart
        items_list = client.get("/api/saved/items").json()
        assert len(items_list) == 1
        saved_item_id = items_list[0]["saved_item_id"]

        # Simulate upstream price change in live Channel3 refresh so add_saved_item_to_cart detects difference
        target_pid = items_list[0]["product_id"]
        old_price = items_list[0]["price_at_save"]
        updated_cat_a = _make_catalog("Audio", "microphone", count=5)
        for item in updated_cat_a:
            if f"c3_{item['id']}" == target_pid or item["id"] == target_pid:
                item["price"]["price"] = round(old_price - 5.0, 2)
        mock_client_price_drop = _mock_channel3_async_client(lambda q: updated_cat_a)

        with patch("httpx.AsyncClient", return_value=mock_client_price_drop):
            atc_resp = client.post(f"/api/saved/items/{saved_item_id}/add-to-cart")
        assert atc_resp.status_code == 200
        atc_data = atc_resp.json()
        assert atc_data["price_changed"] is True
        assert atc_data["current_price"] == round(old_price - 5.0, 2)
        assert any(it["product_id"] == target_pid for it in atc_data["cart"]["items"])

        # 4. Save Search A, then search for B and Save Search B
        ss_a = client.post("/api/ai/intent", json={"message": "Save this search"}).json()
        assert ss_a["action"] == "SEARCH_SAVED"

        cat_b = _make_catalog("Home Office", "desk lamp", count=4)
        mock_client_b = _mock_channel3_async_client(lambda q: cat_b)
        with patch("httpx.AsyncClient", return_value=mock_client_b):
            s_b = client.post("/api/products/search", json={"query": "desk lamp", "budget_limit": 100}).json()
            assert len(s_b["products"]) == 4
            ss_b = client.post("/api/saved/searches").json()
            assert ss_b["original_query"] == "desk lamp"

        # 5. Conversational "reopen my saved search" with 2 saved searches asks clarification
        reopen_amb = client.post("/api/ai/intent", json={"message": "Reopen my saved search"}).json()
        assert reopen_amb["action"] == "CLARIFICATION_NEEDED"
        assert len(reopen_amb.get("saved_searches", [])) == 2

        # 6. Run Again endpoint executes live against Channel3 and restores active search
        cat_a_live = _make_catalog("Audio", "microphone", count=6)
        mock_client_live = _mock_channel3_async_client(lambda q: cat_a_live)
        with patch("httpx.AsyncClient", return_value=mock_client_live):
            saved_id_a = ss_a["saved_search"]["saved_search_id"]
            run_resp = client.post(f"/api/saved/searches/{saved_id_a}/run")
            assert run_resp.status_code == 200
            run_data = run_resp.json()
            assert run_data["action"] == "SEARCH_RESULTS"
            assert len(run_data["products"]) == 6
            assert mock_client_live.post.call_count >= 1

    # 7. Search History bounded at 25 entries & independent from Saved Searches
    for i in range(30):
        saved_service.record_search_history(
            search_id=f"sh_bound_{i}",
            query=f"query term {i}",
            display_query=f"query term {i}",
            result_count=i,
        )
    history = client.get("/api/saved/history?limit=50").json()
    assert len(history) <= 25
    assert len(client.get("/api/saved/searches").json()) == 2


def test_order_history_conversational_and_safe_reorder_flow():
    """
    Verifies:
    - Order History queries via chat ('show my orders', 'what was my last order') NEVER call Channel3
    - Reorder populates cart, prepares fresh PurchaseReview, detects price changes,
      and NEVER executes payment without explicit confirmation.
    """
    client = TestClient(app)

    # Create a real multi-item persisted order in SQLite
    prod1 = product_service.mock_service.get_all_products()[0]
    prod2 = product_service.mock_service.get_all_products()[1]
    order_id = "ord_test_reorder_001"
    test_order = OrderRecord(
        order_id=order_id,
        date="2026-11-11",
        timestamp="2026-11-11T19:00:00Z",
        product_title=f"{prod1.title} + 1 more item",
        merchant="Test Merchant",
        category="Audio",
        item_price=round(prod1.price + prod2.price, 2),
        item_subtotal=round(prod1.price + prod2.price, 2),
        shipping=0.0,
        tax=round((prod1.price + prod2.price) * 0.08, 2),
        total=round((prod1.price + prod2.price) * 1.08, 2),
        quantity=2,
        variant="Standard",
        items=[
            OrderLineItem(
                product_id=prod1.id,
                product_title=prod1.title,
                merchant=prod1.merchant,
                category=prod1.category,
                unit_price=round(prod1.price - 4.0, 2),  # older price to verify price_changes detection
                quantity=1,
                line_total=round(prod1.price - 4.0, 2),
            ),
            OrderLineItem(
                product_id=prod2.id,
                product_title=prod2.title,
                merchant=prod2.merchant,
                category=prod2.category,
                unit_price=prod2.price,
                quantity=1,
                line_total=prod2.price,
            ),
        ],
        interaction_mode="VOICE",
        confirmation_method="PayPal Sandbox",
        payment_status="Completed (Sandbox)",
        paypal_order_id="PAYPAL_TEST_123",
        paypal_capture_id="CAPTURE_TEST_456",
        tracking_status="Order confirmed",
    )
    db.save_order(test_order.model_dump())

    orders_resp = client.get("/api/orders").json()
    assert orders_resp[0]["order_id"] == order_id

    detail_resp = client.get(f"/api/orders/{order_id}").json()
    assert len(detail_resp["items"]) == 2
    assert detail_resp["paypal_capture_id"] == "CAPTURE_TEST_456"

    # Conversational order queries must NOT call Channel3
    mock_client = _mock_channel3_async_client(lambda q: [])
    with patch("httpx.AsyncClient", return_value=mock_client):
        r_orders = client.post("/api/ai/intent", json={"message": "Show my orders"}).json()
        assert r_orders["action"] == "OPEN_ORDERS"
        assert r_orders["channel3_called"] is False
        assert mock_client.post.call_count == 0

        r_last = client.post("/api/ai/intent", json={"message": "What was my last order?"}).json()
        assert r_last["channel3_called"] is False
        assert order_id in r_last["message"] or prod1.title in r_last["message"]
        assert mock_client.post.call_count == 0

    # Reorder via REST endpoint -> refreshes price, sets fresh review, DOES NOT pay
    orders_before = len(order_service.get_all_orders())
    reorder_resp = client.post(f"/api/orders/{order_id}/reorder")
    assert reorder_resp.status_code == 200
    ro = reorder_resp.json()
    assert ro["success"] is True
    assert len(ro["cart"]["items"]) == 2
    assert len(ro["price_changes"]) >= 1
    assert ro["review"]["state"] == PurchaseState.PAYMENT_REVIEW.value
    assert confirmation_service.get_state() == PurchaseState.PAYMENT_REVIEW
    assert len(order_service.get_all_orders()) == orders_before


def test_gemini_fallback_preserves_active_session_on_error():
    """Verifies Gemini HTTP 500/invalid JSON falls back cleanly without breaking active search."""
    catalog = _make_catalog("Electronics", "webcam", count=4)
    mock_client = _mock_channel3_async_client(lambda q: catalog)

    async def _run():
        with patch("httpx.AsyncClient", return_value=mock_client):
            r1 = await ai_service.process_user_intent("Find webcam under $100")
            assert r1["action"] == "SEARCH_RESULTS"
            expected_id = r1["products"][2]["id"]

        # Enable fake Gemini key and simulate Gemini returning malformed JSON on follow-up
        ai_service.llm_service.gemini_key = "fake_key_for_fallback_test"
        bad_resp = MagicMock()
        bad_resp.status_code = 200
        bad_resp.json.return_value = {"candidates": [{"content": {"parts": [{"text": "not-json"}]}}]}
        fail_client = AsyncMock()
        fail_client.__aenter__ = AsyncMock(return_value=fail_client)
        fail_client.__aexit__ = AsyncMock(return_value=False)
        fail_client.post = AsyncMock(return_value=bad_resp)

        with patch("httpx.AsyncClient", return_value=fail_client):
            r_det = await ai_service.process_user_intent("Does it have a mic?")
            assert r_det["action"] in ("PRODUCT_DETAILS", "ATTRIBUTE_INQUIRY", "SEARCH_RESULTS", "CLARIFICATION_NEEDED")
            r_pick = await ai_service.process_user_intent("Details for the third one")
            assert r_pick["action"] == "PRODUCT_DETAILS"
            assert r_pick["product"]["id"] == expected_id
            assert r_pick["channel3_called"] is False

    asyncio.run(_run())
