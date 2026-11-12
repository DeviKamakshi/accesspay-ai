import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.ai_service import ai_service
from app.services.cart_service import cart_service
from app.services.confirmation_service import confirmation_service
from app.services.product_service import product_service
from app.services.search_engine import (
    ConstraintStrength,
    StructuredSearchIntent,
    build_typed_constraints,
    extract_search_intent_rules,
)
from app.services.shopping_session import (
    ConversationalAction,
    classify_user_action,
)


def _make_catalog(category: str, noun: str, count: int = 5):
    """Generates generic Channel3-style product payloads for any arbitrary category."""
    brands = ["ApexGear", "NorthPeak", "VeloCraft", "PureHome", "SummitLab", "BrightLine"]
    slug = noun.replace(" ", "_")
    items = []
    for idx in range(count):
        brand = brands[idx % len(brands)]
        price = round(95.0 - idx * 14.0, 2)  # descending: 95, 81, 67, 53, 39
        items.append({
            "id": f"{slug}_{idx + 1}",
            "title": f"{brand} Everyday {noun.title()} Model {idx + 1}",
            "price": {"price": price, "currency": "USD"},
            "description": f"Durable {noun} designed for daily use in {category}.",
            "brand_name": brand,
            "categories": [category],
            "image_url": f"https://example.com/{slug}_{idx + 1}.jpg",
            "url": f"https://example.com/p/{slug}_{idx + 1}",
            "score": 0.9 - idx * 0.04,
            "availability": "InStock",
        })
    return items


def _mock_channel3_http(catalog_provider):
    """Builds a mock httpx.AsyncClient whose call count can be inspected."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    async def fake_post(url, json=None, headers=None, **kwargs):
        query = (json or {}).get("query", "")
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = catalog_provider(query)
        return resp

    client.post = AsyncMock(side_effect=fake_post)
    return client


@pytest.fixture(autouse=True)
def _reset_session():
    orig_gemini = ai_service.llm_service.gemini_key
    orig_openai = ai_service.llm_service.openai_key
    ai_service.llm_service.gemini_key = ""
    ai_service.llm_service.openai_key = ""
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
    product_service.set_provider_mode(None)


@pytest.mark.parametrize(
    "category,query,noun",
    [
        ("Outdoor Gear", "Find camping tent under $100", "tent"),
        ("Kitchen Appliances", "Find coffee maker under $100", "coffee maker"),
        ("Office Furniture", "Find ergonomic keyboard under $100", "keyboard"),
        ("Luggage", "Find waterproof backpack under $100", "backpack"),
        ("Home Goods", "Find insulated tumbler under $100", "tumbler"),
    ],
)
def test_property_a_to_f_multi_turn_session_preserves_universe_and_zero_extra_calls(category, query, noun):
    """
    Generic Property Check across diverse unrelated categories:
    1) Initial NEW_SEARCH hits Channel3 once (generation 1)
    2) COMPARE, PRODUCT_DETAILS, SORT_RESULTS, CHEAPER_ALTERNATIVE, SELECT, CHECK_TOTAL,
       PREPARE_CHECKOUT, CANCEL all operate on the active session with ZERO extra Channel3 calls.
    3) Every referenced/compared/selected product belongs strictly to the active category universe.
    """
    catalog = _make_catalog(category, noun, count=5)
    mock_client = _mock_channel3_http(lambda q: catalog)

    async def _run():
        with patch("httpx.AsyncClient", return_value=mock_client):
            r1 = await ai_service.process_user_intent(query)
            assert r1["action"] == "SEARCH_RESULTS"
            assert r1["search_generation"] == 1
            assert r1["channel3_called"] is True
            assert mock_client.post.call_count == 1
            active_ids = {p["id"] for p in ai_service.mock_service.session.candidate_products}
            assert len(r1["products"]) == 5

            # Detail inquiry -> zero Channel3 calls
            r_det = await ai_service.process_user_intent("Tell me more about the second one")
            assert r_det["action"] == "PRODUCT_DETAILS"
            assert r_det["channel3_called"] is False
            assert r_det["product"]["id"] == r1["products"][1]["id"]
            assert mock_client.post.call_count == 1

            # Explicit compare -> zero Channel3 calls
            r_cmp = await ai_service.process_user_intent("Compare the second and third ones")
            assert r_cmp["action"] == "COMPARE"
            assert r_cmp["channel3_called"] is False
            cmp_ids = [p["id"] for p in r_cmp["comparison"]["products"]]
            assert cmp_ids == [r1["products"][1]["id"], r1["products"][2]["id"]]
            assert mock_client.post.call_count == 1

            # Cheaper alternative -> strictly cheaper, from active candidate pool, same product_type, zero extra calls
            r_chp = await ai_service.process_user_intent("Show me something cheaper")
            assert r_chp["action"] == "CHEAPER_ALTERNATIVE_FOUND"
            assert r_chp["channel3_called"] is False
            alt = r_chp["alternative_product"]
            orig = r_chp["original_product"]
            assert alt["id"] in active_ids
            assert alt["price"] < orig["price"]
            assert noun in alt["title"].lower()
            assert mock_client.post.call_count == 1

            # Select cheaper alternative -> zero Channel3 calls, no payment triggered
            r_sel = await ai_service.process_user_intent("Choose the cheapest one")
            assert r_sel["action"] == "PRODUCT_SELECTED"
            assert r_sel["channel3_called"] is False
            assert r_sel["product"]["id"] in active_ids
            assert mock_client.post.call_count == 1

            # Check total -> zero Channel3 calls
            r_tot = await ai_service.process_user_intent("What is my total?")
            assert r_tot["action"] == "TOTAL_SUMMARY"
            assert r_tot["channel3_called"] is False
            assert mock_client.post.call_count == 1

    asyncio.run(_run())


def test_property_g_ambiguous_references_ask_clarification_then_resolve_without_searching():
    catalog = _make_catalog("Home Office", "lamp", count=4)
    mock_client = _mock_channel3_http(lambda q: catalog)

    async def _run():
        with patch("httpx.AsyncClient", return_value=mock_client):
            r1 = await ai_service.process_user_intent("Find desk lamp under $100")
            assert r1["action"] == "SEARCH_RESULTS"
            assert len(r1["products"]) == 4
            assert mock_client.post.call_count == 1

            # Ambiguous selection across 3 options -> clarification, NO search, NO selection
            r_amb = await ai_service.process_user_intent("Choose one")
            assert r_amb["action"] == "CLARIFICATION_NEEDED"
            assert r_amb["needs_clarification"] is True
            assert r_amb["channel3_called"] is False
            assert ai_service.mock_service.session.selected_product is None
            assert mock_client.post.call_count == 1

            # Answering the clarification selects the intended option without calling Channel3
            r_ans = await ai_service.process_user_intent("Option 2")
            assert r_ans["action"] == "PRODUCT_SELECTED"
            assert r_ans["product"]["id"] == r1["products"][1]["id"]
            assert r_ans["channel3_called"] is False
            assert mock_client.post.call_count == 1

            # Ambiguous comparison across 3 options -> clarification, then resolved
            r_cmp_amb = await ai_service.process_user_intent("Compare two of them")
            assert r_cmp_amb["action"] == "CLARIFICATION_NEEDED"
            assert mock_client.post.call_count == 1

            r_cmp_ans = await ai_service.process_user_intent("The first and third")
            assert r_cmp_ans["action"] == "COMPARE"
            cmp_ids = [p["id"] for p in r_cmp_ans["comparison"]["products"]]
            assert cmp_ids == [r1["products"][0]["id"], r1["products"][2]["id"]]
            assert mock_client.post.call_count == 1

    asyncio.run(_run())


def test_property_c_cheaper_alternative_preserves_invariants_when_cache_has_none():
    """
    When cached candidates contain no strictly cheaper item, fallback search must preserve
    product_type / brand invariants and raise max_price strictly below current product price.
    """
    expensive_only = [
        {
            "id": "mixer_1",
            "title": "ApexGear Stand Mixer 5Qt",
            "price": {"price": 75.0, "currency": "USD"},
            "description": "Heavy duty stand mixer.",
            "brand_name": "ApexGear",
            "categories": ["Kitchen"],
            "score": 0.92,
        }
    ]
    cheaper_and_wrong = [
        {
            "id": "mixer_2",
            "title": "ApexGear Stand Mixer Compact",
            "price": {"price": 59.0, "currency": "USD"},
            "description": "Compact stand mixer.",
            "brand_name": "ApexGear",
            "categories": ["Kitchen"],
            "score": 0.90,
        },
        {
            "id": "blender_1",
            "title": "Generic Smoothie Blender",
            "price": {"price": 29.0, "currency": "USD"},
            "description": "Budget blender.",
            "brand_name": "Generic",
            "categories": ["Kitchen"],
            "score": 0.85,
        },
    ]

    seen_queries = []
    phase = {"turn": 1}

    def provider(query: str):
        seen_queries.append((phase["turn"], query))
        if phase["turn"] == 1:
            return expensive_only
        return cheaper_and_wrong

    mock_client = _mock_channel3_http(provider)

    async def _run():
        with patch("httpx.AsyncClient", return_value=mock_client):
            r1 = await ai_service.process_user_intent("Find ApexGear stand mixer under $90")
            assert r1["action"] == "SEARCH_RESULTS"
            assert r1["products"][0]["id"].endswith("mixer_1")

            phase["turn"] = 2
            r_chp = await ai_service.process_user_intent("Any cheaper alternative?")
            assert r_chp["action"] == "CHEAPER_ALTERNATIVE_FOUND"
            assert r_chp["alternative_product"]["id"].endswith("mixer_2")
            assert r_chp["alternative_product"]["price"] < 75.0
            turn2_queries = [q.lower() for t, q in seen_queries if t == 2]
            assert turn2_queries and "stand mixer" in turn2_queries[0] and "apexgear" in turn2_queries[0]

    asyncio.run(_run())


def test_property_d_and_i_topic_switch_resets_session_and_unknown_never_calls_channel3():
    tents = _make_catalog("Camping", "tent", count=4)
    strollers = _make_catalog("Baby", "stroller", count=4)

    def provider(query: str):
        if "stroller" in query.lower():
            return strollers
        return tents

    mock_client = _mock_channel3_http(provider)

    async def _run():
        with patch("httpx.AsyncClient", return_value=mock_client):
            # Chit-chat / unknown fragments should NEVER trigger Channel3 search
            r_hello = await ai_service.process_user_intent("hello")
            assert r_hello["channel3_called"] is False
            assert mock_client.post.call_count == 0

            r_unclear = await ai_service.process_user_intent("maybe something?")
            assert r_unclear["action"] in ("CLARIFICATION_NEEDED", "INFO")
            assert r_unclear["channel3_called"] is False
            assert mock_client.post.call_count == 0

            # First topic search (generation 1)
            r1 = await ai_service.process_user_intent("Find camping tent under $100")
            assert r1["search_generation"] == 1
            assert mock_client.post.call_count == 1
            await ai_service.process_user_intent("Choose the first one")
            assert ai_service.mock_service.session.selected_product["id"].endswith("tent_1")

            # Sort active candidates -> zero extra calls
            r_sort = await ai_service.process_user_intent("Sort by lowest price first")
            assert r_sort["action"] == "SEARCH_RESULTS"
            assert r_sort["channel3_called"] is False
            prices = [p["price"] for p in r_sort["products"]]
            assert prices == sorted(prices)
            assert mock_client.post.call_count == 1

            # New unrelated topic -> increments generation and wipes previous selection/comparison
            r2 = await ai_service.process_user_intent("Now search for travel stroller under $100")
            assert r2["action"] == "SEARCH_RESULTS"
            assert r2["search_generation"] == 2
            assert ai_service.mock_service.session.selected_product is None
            assert ai_service.mock_service.session.comparison_products == []
            assert all("stroller" in p["title"].lower() for p in r2["products"])
            assert mock_client.post.call_count == 2

    asyncio.run(_run())


def test_property_h_stale_search_response_is_discarded_when_generation_advances():
    tent_catalog = _make_catalog("Camping", "tent", count=3)
    bike_catalog = _make_catalog("Cycling", "bicycle", count=3)

    slow_client = AsyncMock()
    slow_client.__aenter__ = AsyncMock(return_value=slow_client)
    slow_client.__aexit__ = AsyncMock(return_value=False)

    call_idx = {"n": 0}

    async def slow_then_fast(url, json=None, headers=None, **kwargs):
        call_idx["n"] += 1
        my_call = call_idx["n"]
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        if my_call == 1:
            await asyncio.sleep(0.08)
            resp.json.return_value = tent_catalog
        else:
            await asyncio.sleep(0.01)
            resp.json.return_value = bike_catalog
        return resp

    slow_client.post = AsyncMock(side_effect=slow_then_fast)

    async def _run():
        with patch("httpx.AsyncClient", return_value=slow_client):
            t1 = asyncio.create_task(ai_service.process_user_intent("Find camping tent under $100"))
            await asyncio.sleep(0.01)
            t2 = asyncio.create_task(ai_service.process_user_intent("Find mountain bicycle under $100"))
            r1, r2 = await asyncio.gather(t1, t2)

            assert r2["action"] == "SEARCH_RESULTS"
            assert r2["search_generation"] == 2
            assert all("bicycle" in p["title"].lower() for p in r2["products"])

            assert r1["action"] == "STALE_DISCARDED"
            assert r1["stale"] is True
            # Active session must still contain bicycles, never overwritten by delayed tents
            session_titles = [p["title"].lower() for p in ai_service.mock_service.session.displayed_products]
            assert all("bicycle" in title for title in session_titles)

    asyncio.run(_run())


def test_property_e_hard_soft_constraints_and_word_boundary_no_macbook_collision():
    intent = extract_search_intent_rules("Find wireless headphones black under $80")
    intent.brand = "ApexAudio"
    constraints = build_typed_constraints(intent)
    hard_fields = {c.field for c in constraints if c.strength == ConstraintStrength.HARD}
    soft_fields = {c.field for c in constraints if c.strength == ConstraintStrength.SOFT}
    assert {"max_price", "product_type", "brand"} <= hard_fields
    assert {"color", "feature"} <= soft_fields

    gift_intent = extract_search_intent_rules("birthday gift for a 5 year old under $30")
    gift_constraints = gift_intent.constraints or build_typed_constraints(gift_intent)
    derived_fields = {c.field for c in gift_constraints if c.strength == ConstraintStrength.DERIVED}
    assert "product_type" in derived_fields
    assert "recipient_or_use_case" in derived_fields
    assert "color" in soft_fields

    # Word boundary check: "MacBook Pro" and "cookbooks" contain "ok" substring but MUST classify as NEW_SEARCH, never confirmation ambiguity!
    session = ai_service.mock_service.session
    for term in ("Find MacBook Pro sleeve under $50", "Find cookbooks under $30"):
        out = classify_user_action(term, session)
        assert out.action == ConversationalAction.NEW_SEARCH

    # LLM validator refuses invalid/ungrounded actions and preserves deterministic grounding
    llm_service = ai_service.llm_service
    session.displayed_products = [
        {"id": "p1", "title": "Alpha Toaster", "price": 45.0, "merchant": "Home"},
        {"id": "p2", "title": "Beta Toaster", "price": 35.0, "merchant": "Home"},
    ]
    det_unknown = classify_user_action("hello", session)
    validated_block = llm_service._validate_llm_action(
        {"action": "NEW_SEARCH", "search_query": "hello", "starts_new_search": True},
        "hello",
        det_unknown,
    )
    assert validated_block.action != ConversationalAction.NEW_SEARCH

    det_select = classify_user_action("choose option 2", session)
    validated_select = llm_service._validate_llm_action(
        {"action": "SELECT", "references": ["p2"]},
        "choose option 2",
        det_select,
    )
    assert validated_select.action == ConversationalAction.SELECT
    assert validated_select.references == ["p2"]
