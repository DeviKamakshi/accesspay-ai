import asyncio
from unittest.mock import AsyncMock, patch

from app.models.product import Product
from app.services.ai_service import MockAIService
from app.services.product_service import Channel3ProductService
from app.services.search_engine import (
    extract_search_intent_rules,
    is_followup_refinement_command,
    score_and_filter_candidates,
)


def _make_product(
    pid: str,
    title: str,
    price: float,
    category: str = "Electronics",
    brands=None,
    description: str = "",
    features=None,
    attributes=None,
) -> Product:
    attrs = dict(attributes or {})
    if brands is not None:
        attrs["brands"] = brands
    return Product(
        id=pid,
        title=title,
        price=price,
        currency="USD",
        category=category,
        description=description or title,
        documented_accessibility_features=features or [],
        attributes=attrs,
    )


def test_noise_cancelling_query_does_not_trigger_cancel_intent():
    """'cancelling' contains 'cancel' as a substring and must search, not cancel."""
    intent = extract_search_intent_rules("noise cancelling headphones under $100")
    assert "headphones" in intent.search_query.lower()
    assert intent.max_price == 100.0
    assert "noise cancelling" in intent.features

    mock_ai = MockAIService()
    mock_result = {
        "products": [
            _make_product(
                "h1",
                "Acme ANC Wireless Headphones",
                79.99,
                category="Audio",
                features=["Noise Cancelling"],
            )
        ],
        "error": None,
        "budget_exceeded": False,
        "above_budget_products": [],
        "provider": "channel3",
    }
    with patch("app.services.ai_service.product_service.search_products", new=AsyncMock(return_value=mock_result)):
        res = asyncio.run(mock_ai.process_user_intent("noise cancelling headphones under $100"))
    assert res["action"] == "SEARCH_RESULTS"
    assert len(res["products"]) == 1


def test_brand_anchor_filters_unrelated_products_generically():
    """If candidate pool shows a query token is a brand, unrelated items must be filtered out."""
    candidates = [
        _make_product("p1", "Acme Running Shoes", 75.0, category="Shoes", brands=["Acme"]),
        _make_product("p2", "OtherCo Running Shoes", 45.0, category="Shoes", brands=["OtherCo"]),
        _make_product("p3", "Acme Water Bottle", 18.0, category="Drinkware", brands=["Acme"]),
    ]
    intent = extract_search_intent_rules("Acme running shoes under $100")
    kept, removed, _ = score_and_filter_candidates(candidates, intent, enforce_budget=True)

    assert [p.id for p in kept] == ["p1"]
    assert any(r["reason"].startswith("missing_anchor_brand") for r in removed)
    assert any(r["reason"] == "unrelated_product_type" for r in removed)


def test_standalone_product_outranks_combo_bundle():
    """A standalone keyboard/device should rank above a multi-item combo when user didn't ask for a combo."""
    candidates = [
        _make_product("combo", "Acme Z9 Wireless Keyboard & Mouse Combo", 129.99, category="Keyboards", brands=["Acme"]),
        _make_product("solo", "Acme Z9 Wireless Keyboard", 109.99, category="Keyboards", brands=["Acme"]),
    ]
    intent = extract_search_intent_rules("Acme Z9 keyboard")
    kept, _, _ = score_and_filter_candidates(candidates, intent, enforce_budget=True)
    assert [p.id for p in kept] == ["solo", "combo"]


def test_model_token_and_accessory_filtering_triggers_budget_exceeded():
    """Accessories and non-matching models must not satisfy a specific model + strict budget."""
    c3 = Channel3ProductService()
    c3.api_key = "test_key"

    under_budget_candidates = [
        _make_product(
            "acc1",
            "Acme Z9 Palm Rest",
            22.99,
            category="Keyboard Accessories",
            brands=["Acme"],
            description="Designed for Acme Z9 Keyboard",
        ),
        _make_product(
            "other_model",
            "Acme Mini Basic Wireless Keyboard",
            34.99,
            category="Keyboards",
            brands=["Acme"],
            description="Compact wireless keyboard",
        ),
    ]
    unbounded_candidates = under_budget_candidates + [
        _make_product(
            "real_z9",
            "Acme Z9 Wireless Keyboard",
            109.99,
            category="Keyboards",
            brands=["Acme"],
            description="Full size illuminated keyboard",
        )
    ]

    async def fake_fetch(client, key, search_str, limit, budget_limit, min_price):
        if budget_limit is not None:
            return [p for p in under_budget_candidates if p.price <= budget_limit]
        return unbounded_candidates

    with patch.object(c3, "_fetch_raw_channel3", side_effect=fake_fetch):
        products = asyncio.run(c3.search("Acme Z9 keyboard under $40", budget_limit=40.0, limit=18))

    assert products == []
    assert [p.id for p in c3.above_budget_candidates] == ["real_z9"]


def test_followup_vs_new_topic_classification():
    """Refinements stay tied to active topic; explicit new searches switch topics."""
    active = extract_search_intent_rules("wireless headphones under $80")
    assert is_followup_refinement_command("Show cheaper ones.", active) is True
    assert is_followup_refinement_command("Only black ones.", active) is True
    assert is_followup_refinement_command("Under $50 instead.", active) is True
    assert is_followup_refinement_command("Show another brand.", active) is True

    assert is_followup_refinement_command("Now find a backpack under $40.", active) is False
    assert is_followup_refinement_command("water bottle under $25", active) is False
    assert is_followup_refinement_command("USB-C charger for iPhone", active) is False


def test_decorations_posters_costumes_rejected_for_franchise_toys():
    """Brand/character match alone must not pass banners, inflatables, blow molds, posters, or costumes as toys."""
    from app.services.search_engine import build_broadened_queries

    intent = extract_search_intent_rules("CartoonX toys")
    broadened = build_broadened_queries(intent)
    assert "CartoonX toys" in broadened
    assert "CartoonX toy" in broadened
    assert "CartoonX plush" in broadened
    assert "CartoonX figure" in broadened
    assert "CartoonX playset" in broadened
    assert "CartoonX" not in broadened

    candidates = [
        _make_product("dec1", "CartoonX Birthday Banner Decoration", 12.99, category="Party Supplies", brands=["CartoonX"]),
        _make_product("dec2", "CartoonX Halloween Inflatable Decoration", 49.99, category="Toys & Games", brands=["CartoonX"]),
        _make_product("dec3", "CartoonX Halloween Blow Mold Decoration Set", 39.99, category="Seasonal", brands=["CartoonX"]),
        _make_product("dec4", "CartoonX Wall Poster", 9.99, category="Wall Art", brands=["CartoonX"]),
        _make_product("app1", "CartoonX Toddler Costume", 29.99, category="Costumes", brands=["CartoonX"]),
        _make_product("other_toy", "OtherBrand Soft Plush Toy", 15.00, category="Stuffed Animals", brands=["OtherBrand"]),
        _make_product("toy1", "CartoonX Sleepytime Soft Toy", 24.50, category="Stuffed Animals", brands=["CartoonX"]),
        _make_product("toy2", "CartoonX Bath Playset", 10.99, category="Bath Toys", brands=["CartoonX"]),
    ]
    kept, removed, _ = score_and_filter_candidates(candidates, intent, enforce_budget=True)
    assert [p.id for p in kept] == ["toy1", "toy2"]
    assert len(removed) == 6


def test_product_type_mismatches_rejected_across_categories():
    """Verify generic exclusion of shoe bags/shirts, speakers, and bottle cleaning brushes."""
    shoe_intent = extract_search_intent_rules("RunnerCo running shoes")
    shoe_pool = [
        _make_product("s_bag", "RunnerCo Shoe Bag", 19.99, category="Bags", brands=["RunnerCo"]),
        _make_product("s_shirt", "RunnerCo Running T-Shirt", 35.00, category="Shirts", brands=["RunnerCo"]),
        _make_product("s_real", "RunnerCo Swift Running Shoes", 84.99, category="Athletic Shoes", brands=["RunnerCo"]),
    ]
    kept_shoes, _, _ = score_and_filter_candidates(shoe_pool, shoe_intent)
    assert [p.id for p in kept_shoes] == ["s_real"]

    audio_intent = extract_search_intent_rules("wireless headphones")
    audio_pool = [
        _make_product("a_spk", "Acme Wireless Bluetooth Speaker", 45.00, category="Speakers"),
        _make_product("a_case", "Protective Carrying Case for Wireless Headphones", 12.99, category="Cases"),
        _make_product("a_real", "Acme Wireless Over-Ear Headphones", 59.99, category="Headphones"),
    ]
    kept_audio, _, _ = score_and_filter_candidates(audio_pool, audio_intent)
    assert [p.id for p in kept_audio] == ["a_real"]

    bottle_intent = extract_search_intent_rules("water bottle")
    bottle_pool = [
        _make_product("b_brush", "Water Bottle Cleaning Brush", 7.99, category="Cleaning Tools"),
        _make_product("b_real", "Insulated Water Bottle 17oz", 17.40, category="Water Bottles"),
    ]
    kept_bottles, _, _ = score_and_filter_candidates(bottle_pool, bottle_intent)
    assert [p.id for p in kept_bottles] == ["b_real"]

