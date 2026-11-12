from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.db.database import db
from app.db.seed_data import ensure_database_seeded
from app.services.ai_service import ai_service
from app.services.cart_service import cart_service
from app.services.product_service import product_service
from app.services.shopping_session import normalize_conversational_transcript


def _make_catalog(category: str, noun: str, count: int = 8):
    brands = ["NorthPeak", "VeloCraft", "ApexGear", "BrightLine", "SummitLab", "PureHome"]
    slug = noun.replace(" ", "_")
    items = []
    for idx in range(count):
        brand = brands[idx % len(brands)]
        price = round(58.0 - idx * 5.0, 2)
        items.append({
            "id": f"{slug}_{idx + 1}",
            "title": f"{brand} {noun.title()} Edition {idx + 1}",
            "price": {"price": price, "currency": "USD"},
            "description": f"Reliable {noun} designed for everyday {category}.",
            "brand_name": brand,
            "categories": [category],
            "image_url": f"https://example.com/{slug}_{idx + 1}.jpg",
            "url": f"https://example.com/p/{slug}_{idx + 1}",
            "score": 0.96 - idx * 0.03,
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
    yield
    ai_service.llm_service.gemini_key = orig_gemini
    ai_service.llm_service.openai_key = orig_openai
    cart_service.clear()


def _catalog_router(query: str):
    q = query.lower()
    if "kettle" in q:
        return _make_catalog("Kitchen", "ceramic kettle")
    if "shoes" in q or "running" in q:
        return _make_catalog("Footwear", "running shoes")
    return _make_catalog("Drinkware", "water bottle")


def test_transcript_normalization_preserves_keywords_and_fixes_ordinal_homophones():
    assert normalize_conversational_transcript("  Compare the first two options. ") == "Compare the first two options"
    assert normalize_conversational_transcript("Compare the first to options!") == "Compare the first two options"
    assert normalize_conversational_transcript("Select option won.") == "Select option one"
    assert normalize_conversational_transcript("Is option 2 waterproof?") == "Is option 2 waterproof?"
    assert normalize_conversational_transcript("   ...   ") == ""


def _patch_channel3(catalog_fn):
    return patch(
        "app.services.product_service.httpx.AsyncClient",
        side_effect=lambda *args, **kwargs: _mock_channel3_async_client(catalog_fn),
    )


def test_voice_and_text_and_chip_produce_identical_followups_without_calling_channel3():
    client = TestClient(app)

    def run_sequence(modes):
        ai_service.reset_conversation()
        cart_service.clear()
        outputs = []
        with _patch_channel3(_catalog_router):

            r_search = client.post("/api/ai/intent", json={
                "message": "Find water bottle under $60",
                "input_mode": modes[0],
            }).json()
            visible_ids = r_search["displayed_product_ids"]
            search_id = r_search["search_id"]
            gen = r_search["search_generation"]
            assert len(visible_ids) >= 3
            assert r_search["channel3_called"] is True

            r_compare = client.post("/api/ai/intent", json={
                "message": "Compare the first two options",
                "input_mode": modes[1],
                "active_search_id": search_id,
                "search_generation": gen,
                "visible_product_ids": visible_ids,
            }).json()
            assert r_compare["action"] == "COMPARE"
            assert r_compare["channel3_called"] is False
            comp_ids = [p["id"] for p in r_compare["comparison"]["products"]]
            assert comp_ids == visible_ids[:2]

            r_details = client.post("/api/ai/intent", json={
                "message": "Tell me about the first option",
                "input_mode": modes[2],
                "active_search_id": search_id,
                "search_generation": gen,
                "visible_product_ids": visible_ids,
            }).json()
            assert r_details["action"] == "PRODUCT_DETAILS"
            assert r_details["channel3_called"] is False
            assert r_details["product"]["id"] == visible_ids[0]

            r_select = client.post("/api/ai/intent", json={
                "message": "Choose the second one",
                "input_mode": modes[3],
                "active_search_id": search_id,
                "search_generation": gen,
                "visible_product_ids": visible_ids,
            }).json()
            assert r_select["action"] == "PRODUCT_SELECTED"
            assert r_select["channel3_called"] is False
            assert r_select["product"]["id"] == visible_ids[1]

            outputs.append((r_compare["action"], comp_ids, r_compare["search_id"], r_compare["search_generation"], r_compare["channel3_called"]))
            outputs.append((r_details["action"], r_details["resolved_product_ids"], r_details["search_id"], r_details["search_generation"], r_details["channel3_called"]))
            outputs.append((r_select["action"], r_select["resolved_product_ids"], r_select["search_id"], r_select["search_generation"], r_select["channel3_called"]))
        return visible_ids, outputs

    vis_voice, out_voice = run_sequence(["voice", "voice", "voice", "voice"])
    vis_text, out_text = run_sequence(["text", "text", "text", "text"])
    vis_chip, out_chip = run_sequence(["command_chip", "command_chip", "command_chip", "command_chip"])

    assert vis_voice == vis_text == vis_chip
    # Actions, resolved product IDs, search_generation, and channel3_called are identical
    for v_step, t_step, c_step in zip(out_voice, out_text, out_chip):
        assert (v_step[0], v_step[1], v_step[3], v_step[4]) == (t_step[0], t_step[1], t_step[3], t_step[4])
        assert (v_step[0], v_step[1], v_step[3], v_step[4]) == (c_step[0], c_step[1], c_step[3], c_step[4])


def test_mixed_voice_text_and_mode_switch_preserve_active_product_context():
    client = TestClient(app)

    with _patch_channel3(_catalog_router):

        # 1. Text search -> Voice compare -> Mode switch -> Voice select
        s1 = client.post("/api/ai/intent", json={
            "message": "Find running shoes under $60",
            "input_mode": "text",
        }).json()
        vis1 = s1["displayed_product_ids"]
        sid1 = s1["search_id"]
        gen1 = s1["search_generation"]
        assert len(vis1) >= 3 and all(pid.startswith("c3_running_shoes_") for pid in vis1), f"Unexpected s1={s1}"

        # Accessibility mode switches must NEVER clear active search or cart
        for mode in ("VOICE", "KEYBOARD", "LARGE_CONTROLS", "SWITCH", "VOICE"):
            m_res = client.post("/api/accessibility/mode", json={"mode": mode})
            assert m_res.status_code == 200

        c1 = client.post("/api/ai/intent", json={
            "message": "Compare the first to options.",
            "raw_transcript": "Compare the first to options.",
            "input_mode": "voice",
            "active_search_id": sid1,
            "search_generation": gen1,
            "visible_product_ids": vis1,
        }).json()
        assert c1["action"] == "COMPARE"
        assert c1["channel3_called"] is False
        assert [p["id"] for p in c1["comparison"]["products"]] == vis1[:2]

        # Empty voice transcript asks to repeat and NEVER triggers Channel3
        empty_res = client.post("/api/ai/intent", json={
            "message": "   ... ",
            "raw_transcript": "   ",
            "input_mode": "voice",
            "active_search_id": sid1,
            "search_generation": gen1,
            "visible_product_ids": vis1,
        }).json()
        assert empty_res["action"] == "CLARIFICATION_NEEDED"
        assert empty_res["channel3_called"] is False

        # Voice cheaper alternative stays inside running shoes
        cheap_res = client.post("/api/ai/intent", json={
            "message": "Show something cheaper",
            "input_mode": "voice",
            "active_search_id": sid1,
            "search_generation": gen1,
            "visible_product_ids": vis1,
        }).json()
        assert cheap_res["action"] in ("CHEAPER_ALTERNATIVE_FOUND", "SEARCH_RESULTS")
        if cheap_res["action"] == "CHEAPER_ALTERNATIVE_FOUND":
            assert cheap_res["alternative_product"]["id"].startswith("c3_running_shoes_")
        else:
            assert all(p["id"].startswith("c3_running_shoes_") for p in cheap_res["products"])

        # Voice select second option adds to cart
        sel_res = client.post("/api/ai/intent", json={
            "message": "Choose the second one",
            "input_mode": "voice",
            "active_search_id": sid1,
            "search_generation": gen1,
            "visible_product_ids": vis1,
        }).json()
        assert sel_res["action"] == "PRODUCT_SELECTED"
        assert sel_res["product"]["id"] == vis1[1]

        # 2. Explicit new voice search switches generation cleanly while keeping cart item
        s2 = client.post("/api/ai/intent", json={
            "message": "Now find ceramic kettle under $60",
            "input_mode": "voice",
            "active_search_id": sid1,
            "search_generation": gen1,
            "visible_product_ids": vis1,
        }).json()
        assert s2["action"] == "SEARCH_RESULTS"
        assert s2["search_generation"] > gen1
        assert s2["search_id"] != sid1
        assert all(pid.startswith("c3_ceramic_kettle_") for pid in s2["displayed_product_ids"])
        assert cart_service.get_cart().item_count == 1

        c2 = client.post("/api/ai/intent", json={
            "message": "Compare the first two options",
            "input_mode": "voice",
            "active_search_id": s2["search_id"],
            "search_generation": s2["search_generation"],
            "visible_product_ids": s2["displayed_product_ids"],
        }).json()
        assert c2["action"] == "COMPARE"
        assert c2["channel3_called"] is False
        assert [p["id"] for p in c2["comparison"]["products"]] == s2["displayed_product_ids"][:2]


def test_visible_product_ids_reconciles_card_order_for_voice_ordinals():
    client = TestClient(app)

    with _patch_channel3(_catalog_router):

        s1 = client.post("/api/ai/intent", json={
            "message": "Find ceramic kettle under $60",
            "input_mode": "voice",
        }).json()
        vis = s1["displayed_product_ids"]
        reordered = [vis[2], vis[0], vis[1]] + vis[3:]

        c_res = client.post("/api/ai/intent", json={
            "message": "Compare the first two options",
            "input_mode": "voice",
            "active_search_id": s1["search_id"],
            "search_generation": s1["search_generation"],
            "visible_product_ids": reordered,
        }).json()
        assert c_res["action"] == "COMPARE"
        assert c_res["channel3_called"] is False
        assert [p["id"] for p in c_res["comparison"]["products"]] == [vis[2], vis[0]]


def test_long_multi_turn_voice_session_never_forgets_or_wipes_active_products():
    """Verify 12+ consecutive voice follow-ups keep the exact active search until an explicit new search."""
    client = TestClient(app)

    with _patch_channel3(_catalog_router):
        # Turn 1: Initial Voice Search
        s1 = client.post("/api/ai/intent", json={
            "message": "Find water bottle under $60",
            "raw_transcript": "Find water bottle under $60",
            "input_mode": "voice",
        }).json()
        sid1 = s1["search_id"]
        gen1 = s1["search_generation"]
        vis1 = s1["displayed_product_ids"]
        assert s1["action"] == "SEARCH_RESULTS"
        assert len(vis1) >= 3
        assert all(pid.startswith("c3_water_bottle_") for pid in vis1)

        def post_voice(text, vis_override=None):
            return client.post("/api/ai/intent", json={
                "message": text,
                "raw_transcript": text,
                "input_mode": "voice",
                "active_search_id": sid1,
                "search_generation": gen1,
                "visible_product_ids": vis_override if vis_override is not None else vis1,
            }).json()

        # Turns 2-10: Diverse follow-up phrasings in voice mode
        t2 = post_voice("Compare the first two options")
        assert t2["action"] == "COMPARE"
        assert t2["channel3_called"] is False
        assert t2["search_id"] == sid1 and t2["search_generation"] == gen1
        assert [p["id"] for p in t2["comparison"]["products"]] == vis1[:2]

        t3 = post_voice("Tell me about the second one")
        assert t3["action"] == "PRODUCT_DETAILS"
        assert t3["channel3_called"] is False
        assert t3["search_id"] == sid1 and t3["search_generation"] == gen1
        assert t3["resolved_product_ids"] == [vis1[1]]

        t4 = post_voice("Which one is better?")
        assert t4["action"] in ("COMPARE", "RECOMMENDATION", "ATTRIBUTE_INQUIRY", "PRODUCT_DETAILS")
        assert "search for products first" not in t4["message"].lower()
        assert t4["search_id"] == sid1 and t4["search_generation"] == gen1

        t5 = post_voice("Which one is cheaper?")
        assert t5["action"] in ("PRODUCT_DETAILS", "ATTRIBUTE_INQUIRY")
        assert t5["channel3_called"] is False
        assert "don't have reliable information" not in t5["message"].lower()
        assert "$" in t5["message"]
        assert t5["search_id"] == sid1 and t5["search_generation"] == gen1

        t6 = post_voice("Which has better reviews?")
        assert t6["action"] == "ATTRIBUTE_INQUIRY"
        assert t6["channel3_called"] is False
        assert t6["search_id"] == sid1 and t6["search_generation"] == gen1

        t7 = post_voice("Show something cheaper")
        assert t7["action"] == "CHEAPER_ALTERNATIVE_FOUND"
        assert t7["alternative_product"]["id"].startswith("c3_water_bottle_")
        assert t7["search_id"] == sid1 and t7["search_generation"] == gen1

        t8 = post_voice("Save the first one")
        assert t8["action"] == "PRODUCT_SAVED"
        assert t8["search_id"] == sid1 and t8["search_generation"] == gen1

        t9 = post_voice("Show more")
        assert t9["action"] == "SEARCH_RESULTS"
        assert t9["search_id"] == sid1 and t9["search_generation"] == gen1
        assert len(t9["displayed_product_ids"]) > len(vis1)
        vis_after_more = t9["displayed_product_ids"]
        assert all(pid.startswith("c3_water_bottle_") for pid in vis_after_more)

        t10 = post_voice("Sort by price lowest first", vis_override=vis_after_more)
        assert t10["action"] == "SEARCH_RESULTS"
        assert t10["search_id"] == sid1 and t10["search_generation"] == gen1
        prices = [p["price"] for p in t10["products"]]
        assert prices == sorted(prices)
        vis_sorted = t10["displayed_product_ids"]

        # Turn 11: Soft color refinement preserves water bottle search (never returns unrelated items)
        t11 = post_voice("Only purple ones", vis_override=vis_sorted)
        assert t11["action"] in ("SEARCH_RESULTS", "INFO")
        assert t11["search_id"] == sid1 and t11["search_generation"] == gen1
        assert all(p["id"].startswith("c3_water_bottle_") for p in t11["products"])
        vis_after_color = t11["displayed_product_ids"] or vis_sorted

        # Turn 11b: Hard budget refinement that matches 0 items ("Under $5 instead") MUST preserve active products!
        t11b = post_voice("Under $5 instead", vis_override=vis_after_color)
        assert t11b["action"] == "INFO"
        assert t11b.get("preserve_active_products") is True
        assert t11b["displayed_product_ids"] == vis_after_color
        assert t11b["search_id"] == sid1 and t11b["search_generation"] == gen1

        # Turn 12: Budget refinement ("What about under $50 instead?") keeps same search generation
        t12 = post_voice("What about under $50 instead?", vis_override=vis_after_color)
        assert t12["action"] == "SEARCH_RESULTS"
        assert t12["search_id"] == sid1 and t12["search_generation"] == gen1
        assert all(p["price"] <= 50.0 for p in t12["products"])
        assert all(p["id"].startswith("c3_water_bottle_") for p in t12["products"])
        vis_filtered = t12["displayed_product_ids"]

        # Turn 13: Empty / noise transcript does not clear active search
        t13 = post_voice("   ", vis_override=vis_filtered)
        assert t13["action"] == "CLARIFICATION_NEEDED"
        assert t13["channel3_called"] is False
        assert t13["search_id"] == sid1 and t13["search_generation"] == gen1

        # Turn 14: Voice selection still works cleanly on active filtered list
        t14 = post_voice("Choose the second one", vis_override=vis_filtered)
        assert t14["action"] == "PRODUCT_SELECTED"
        assert t14["product"]["id"] == vis_filtered[1]
        assert t14["search_id"] == sid1 and t14["search_generation"] == gen1

        # Turn 15: Explicit NEW voice search resets cleanly into a new generation
        s2 = client.post("/api/ai/intent", json={
            "message": "Now find ceramic kettle under $60",
            "raw_transcript": "Now find ceramic kettle under $60",
            "input_mode": "voice",
            "active_search_id": sid1,
            "search_generation": gen1,
            "visible_product_ids": vis_filtered,
        }).json()
        assert s2["action"] == "SEARCH_RESULTS"
        assert s2["search_id"] != sid1 and s2["search_generation"] > gen1
        assert all(pid.startswith("c3_ceramic_kettle_") for pid in s2["displayed_product_ids"])

        # Turn 16: Follow-up now compares ONLY the new kettle search, never old water bottles
        c2 = client.post("/api/ai/intent", json={
            "message": "Compare the first two options",
            "raw_transcript": "Compare the first two options",
            "input_mode": "voice",
            "active_search_id": s2["search_id"],
            "search_generation": s2["search_generation"],
            "visible_product_ids": s2["displayed_product_ids"],
        }).json()
        assert c2["action"] == "COMPARE"
        assert c2["channel3_called"] is False
        assert [p["id"] for p in c2["comparison"]["products"]] == s2["displayed_product_ids"][:2]
