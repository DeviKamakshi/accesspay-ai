import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from app.models.purchase import PurchaseState
from app.services.product_service import (
    product_service,
    Channel3ProductService,
    MockProductService,
    Channel3APIError,
)
from app.services.ai_service import ai_service, extract_search_parameters
from app.services.cart_service import cart_service
from app.services.confirmation_service import confirmation_service
from app.services.accessibility_service import accessibility_service
from app.db.seed_data import seed_database


SAMPLE_CHANNEL3_RESPONSE = {
    "products": [
        {
            "id": "wh_ch520",
            "title": "Sony WH-CH520 Wireless Bluetooth Headphones",
            "description": "Wireless on-ear headphones with physical control buttons and 50-hour battery life.",
            "category": "Audio",
            "brands": [{"id": "b_sony", "name": "Sony"}],
            "images": [
                {
                    "url": "https://cdn.trychannel3.com/products/sony-wh-ch520.jpg",
                    "cleaned_url": "https://cdn.trychannel3.com/products/sony-wh-ch520-clean.jpg",
                    "is_main_image": True,
                    "alt_text": "Sony WH-CH520 Wireless Bluetooth Headphones in Black",
                }
            ],
            "attributes": {
                "connectivity": "Wireless Bluetooth 5.2",
                "controls": "Physical tactile buttons",
            },
            "offers": [
                {
                    "domain": "bestbuy.com",
                    "merchant": {"name": "Best Buy", "domain": "bestbuy.com"},
                    "price": {"amount": 59.99, "currency": "USD"},
                    "availability": "InStock",
                    "condition": "new",
                    "url": "https://www.buy.trychannel3.com/offer/wh_ch520",
                }
            ],
        },
        {
            "id": "jbl_tune510",
            "title": "JBL Tune 510BT Wireless On-Ear Headphones",
            "description": "Foldable wireless headphones with multi-point connection and physical earcup buttons.",
            "category": "Audio",
            "brands": [{"id": "b_jbl", "name": "JBL"}],
            "images": [
                {
                    "url": "https://cdn.trychannel3.com/products/jbl-510bt.jpg",
                    "cleaned_url": None,
                    "is_main_image": True,
                    "alt_text": None,
                }
            ],
            "attributes": {
                "connectivity": "Wireless Bluetooth",
                "foldable": "Yes",
            },
            "offers": [
                {
                    "domain": "target.com",
                    "price": {"amount": 44.99, "currency": "USD"},
                    "availability": "InStock",
                    "condition": "new",
                    "url": "https://www.buy.trychannel3.com/offer/jbl_tune510",
                }
            ],
        },
        {
            "id": "anker_q20i",
            "title": "Soundcore Q20i Wireless Noise Cancelling Headphones",
            "description": "Wireless over-ear headphones with oversized tactile switches and 40-hour battery.",
            "category": "Audio",
            "brands": [{"id": "b_soundcore", "name": "Soundcore"}],
            "images": [],
            "attributes": {
                "connectivity": "Wireless",
                "noise_cancelling": "Hybrid ANC",
            },
            "offers": [
                {
                    "domain": "amazon.com",
                    "merchant": {"name": "Amazon", "domain": "amazon.com"},
                    "price": {"amount": 37.99, "currency": "USD"},
                    "availability": "InStock",
                    "condition": "new",
                    "url": "https://www.buy.trychannel3.com/offer/anker_q20i",
                }
            ],
        },
        {
            "id": "koss_porta",
            "title": "Koss Porta Pro Wireless Bluetooth Headphones",
            "description": "Lightweight wireless headphones with inline physical remote controls.",
            "category": "Audio",
            "brands": [{"id": "b_koss", "name": "Koss"}],
            "images": [{"url": "https://cdn.trychannel3.com/products/koss.jpg"}],
            "attributes": {"connectivity": "Wireless"},
            "offers": [
                {
                    "domain": "bhphotovideo.com",
                    "price": {"amount": 49.99, "currency": "USD"},
                    "availability": "InStock",
                    "url": "https://www.buy.trychannel3.com/offer/koss_porta",
                }
            ],
        },
    ]
}


@pytest.fixture(autouse=True)
def setup_phase3_state():
    orig_gemini = ai_service.llm_service.gemini_key
    orig_openai = ai_service.llm_service.openai_key
    orig_c3 = product_service.channel3_service.api_key
    ai_service.llm_service.gemini_key = ""
    ai_service.llm_service.openai_key = ""
    seed_database()
    cart_service.clear()
    confirmation_service.reset()
    accessibility_service.reset_to_defaults()
    ai_service.reset_conversation()
    product_service.set_provider_mode(None)
    product_service.channel3_service.api_call_count = 0
    yield
    ai_service.llm_service.gemini_key = orig_gemini
    ai_service.llm_service.openai_key = orig_openai
    product_service.channel3_service.api_key = orig_c3
    product_service.set_provider_mode(None)


def _mock_httpx_post_success(payload_json=SAMPLE_CHANNEL3_RESPONSE):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload_json

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    return mock_client


def test_scenario_1_real_channel3_search_and_ranking():
    """
    Scenario 1: 'Find wireless headphones under $80.'
    - AI extracts requirements (product_type, max_price=80.0, requirements=['wireless'])
    - Channel3 POST /v1/search is called with x-api-key and price filter
    - Real products are normalized into internal Product model
    - Approximately 3 strong options displayed with BEST MATCH, BEST VALUE, LOWEST PRICE badges
    """
    async def _run():
        product_service.set_provider_mode("channel3")
        product_service.channel3_service.api_key = "test_c3_secret_key"

        mock_client = _mock_httpx_post_success()
        with patch("httpx.AsyncClient", return_value=mock_client):
            res = await ai_service.process_user_intent("Find wireless headphones under $80.")

        assert res["action"] == "SEARCH_RESULTS"
        assert res["product_mode"] == "REAL PRODUCT MODE"
        assert len(res["products"]) == 4

        # Verify Channel3 request payload & headers
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0].endswith("/v1/search")
        assert call_args[1]["headers"]["x-api-key"] == "test_c3_secret_key"
        sent_json = call_args[1]["json"]
        assert sent_json["filters"]["price"]["max_price"] == 80.0
        assert "InStock" in sent_json["filters"]["availability"]

        # Verify product normalization & ranking badges
        p0, p1, p2 = res["products"][:3]
        assert p0["id"].startswith("c3_")
        assert p0["source"] == "channel3"
        assert p0["merchant"] in ["Best Buy", "target.com", "Amazon"]
        assert p0["product_url"].startswith("https://www.buy.trychannel3.com/")
        assert p0["price"] <= 80.0
        badges = {p["ranking_badge"] for p in res["products"]}
        assert "BEST MATCH" in badges
        assert ("LOWEST PRICE" in badges) or ("BEST VALUE" in badges)

    asyncio.run(_run())


def test_scenario_2_compare_first_two_uses_cache_without_new_api_call():
    """
    Scenario 2: 'Compare the first two.'
    - No unnecessary new Channel3 request is made
    - Uses cached product data
    - Returns concise comparison
    """
    async def _run():
        product_service.set_provider_mode("channel3")
        product_service.channel3_service.api_key = "test_c3_secret_key"

        mock_client = _mock_httpx_post_success()
        with patch("httpx.AsyncClient", return_value=mock_client):
            await ai_service.process_user_intent("Find wireless headphones under $80.")
            calls_after_search = product_service.channel3_service.api_call_count
            assert calls_after_search == 1

            comp_res = await ai_service.process_user_intent("Compare the first two.")
            assert comp_res["action"] == "COMPARE"
            # Verify NO new Channel3 API call was made!
            assert product_service.channel3_service.api_call_count == 1
            assert "Option 1" in comp_res["message"]
            assert "Option 2" in comp_res["message"]
            assert "lower-cost choice" in comp_res["message"]

    asyncio.run(_run())


def test_scenario_3_cheaper_alternative_from_channel3_results():
    """
    Scenario 3: 'Show me something cheaper.'
    - Finds a lower-cost product from Channel3 results
    - Concisely reports savings ('I found a similar option for $... less')
    - Does NOT automatically replace selected product
    """
    async def _run():
        product_service.set_provider_mode("channel3")
        product_service.channel3_service.api_key = "test_c3_secret_key"

        mock_client = _mock_httpx_post_success()
        with patch("httpx.AsyncClient", return_value=mock_client):
            await ai_service.process_user_intent("Find wireless headphones under $80.")
            res = await ai_service.process_user_intent("Show me something cheaper.")

        assert res["action"] == "CHEAPER_ALTERNATIVE_FOUND"
        assert res["savings"] > 0
        assert "less" in res["message"]
        assert res["alternative_product"]["price"] < res["original_product"]["price"]
        # Did not auto-select or charge
        assert ai_service.mock_service.selected_product is None
        assert confirmation_service.get_state() == PurchaseState.BROWSING

    asyncio.run(_run())


def test_scenario_4_choose_second_one_selects_real_product_without_payment():
    """
    Scenario 4: 'Choose the second one.'
    - Real Channel3 product selected
    - NO PAYMENT made
    - Continues into existing AccessPay purchase-review flow
    """
    async def _run():
        product_service.set_provider_mode("channel3")
        product_service.channel3_service.api_key = "test_c3_secret_key"

        mock_client = _mock_httpx_post_success()
        with patch("httpx.AsyncClient", return_value=mock_client):
            await ai_service.process_user_intent("Find wireless headphones under $80.")
            sel_res = await ai_service.process_user_intent("Choose the second one.")

        assert sel_res["action"] == "PRODUCT_SELECTED"
        assert sel_res["product"]["source"] == "channel3"
        assert sel_res["product"]["id"].startswith("c3_")
        assert confirmation_service.get_state() != PurchaseState.PAYMENT_COMPLETE
        assert confirmation_service.get_state() != PurchaseState.PAYMENT_PROCESSING

        # Verify seamless transition to Purchase Review
        review = confirmation_service.prepare_payment_review()
        assert review.item_subtotal == sel_res["product"]["price"]
        assert review.state == PurchaseState.PAYMENT_REVIEW

    asyncio.run(_run())


def test_scenario_5_channel3_unavailable_error_handling():
    """
    Scenario 5: Channel3 unavailable
    - When auto-fallback is enabled (default), automatically uses safe mock fallback
    - When auto-fallback is disabled, shows accessible error:
      "I'm having trouble searching right now.\\nPlease try again."
    - Never crashes or exposes raw HTTP 502 / 500 / stack traces
    """
    async def _run():
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Connection timeout")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        # 5a. Default automatic fallback when external service is unavailable
        product_service.set_provider_mode("channel3", allow_fallback=True)
        product_service.channel3_service.api_key = "test_c3_secret_key"
        with patch("httpx.AsyncClient", return_value=mock_client):
            res_auto = await ai_service.process_user_intent("Find wireless headphones under $80.")
        assert res_auto["action"] == "SEARCH_RESULTS"
        assert len(res_auto["products"]) == 3

        # 5b. Strict non-fallback error handling returns clean accessible message
        product_service.set_provider_mode("channel3", allow_fallback=False)
        with patch("httpx.AsyncClient", return_value=mock_client):
            res_err = await ai_service.process_user_intent("Find wireless headphones under $80.")

        assert res_err["action"] == "SEARCH_ERROR"
        assert res_err["error"] is True
        assert res_err["message"] == "I'm having trouble searching right now.\nPlease try again."
        assert "502" not in res_err["message"]
        assert "500" not in res_err["message"]
        assert res_err["products"] == []

    asyncio.run(_run())


def test_resilience_ai_unavailable_invalid_json_and_timeout():
    """
    Tests:
    - AI service unavailable (HTTP 502 / 500) -> falls back to MockAIService seamlessly
    - Invalid API response (malformed JSON) -> falls back seamlessly
    - Request timeout -> falls back seamlessly
    - Unhandled backend exception -> returns clean accessible message without raw error strings
    """
    async def _run():
        product_service.set_provider_mode("mock")
        ai_service.llm_service.gemini_key = "test_gemini_key"

        # 1. AI service returns HTTP 502 Bad Gateway
        bad_resp = MagicMock()
        bad_resp.status_code = 502
        bad_resp.text = "502 Bad Gateway"
        mock_client = AsyncMock()
        mock_client.post.return_value = bad_resp
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client):
            r_502 = await ai_service.process_user_intent("Find wireless headphones under $80.")
        assert r_502["action"] == "SEARCH_RESULTS"
        assert len(r_502["products"]) == 3
        assert "502" not in r_502["message"]

        # 2. Invalid JSON response from AI service
        invalid_json_resp = MagicMock()
        invalid_json_resp.status_code = 200
        invalid_json_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "{not valid json"}]}}]
        }
        mock_client.post.return_value = invalid_json_resp
        with patch("httpx.AsyncClient", return_value=mock_client):
            r_json = await ai_service.process_user_intent("Compare the first two.")
        assert r_json["action"] == "COMPARE"
        assert "Option 1" in r_json["message"]

        # 3. Request timeout
        import httpx
        mock_client.post.side_effect = httpx.TimeoutException("Request timed out")
        with patch("httpx.AsyncClient", return_value=mock_client):
            r_timeout = await ai_service.process_user_intent("Show something cheaper.")
        assert r_timeout["action"] == "CHEAPER_ALTERNATIVE_FOUND"

        ai_service.llm_service.gemini_key = ""

    asyncio.run(_run())


def test_no_results_does_not_invent_products():
    """
    When Channel3 returns 0 matching products:
    - Shows 'I couldn't find a good match. Try changing your budget or product requirements.'
    - Does not invent fallback products
    """
    async def _run():
        product_service.set_provider_mode("channel3")
        product_service.channel3_service.api_key = "test_c3_secret_key"

        mock_client = _mock_httpx_post_success({"products": []})
        with patch("httpx.AsyncClient", return_value=mock_client):
            res = await ai_service.process_user_intent("Find wireless headphones under $5.")

        assert res["action"] == "NO_RESULTS"
        assert res["products"] == []
        assert "I couldn't find a good match." in res["message"]
        assert "Try changing your budget or product requirements." in res["message"]

    asyncio.run(_run())


def test_missing_product_information_never_invented():
    """
    When Channel3 does not provide an attribute (e.g., waterproof rating or weight):
    - Responds with: "I don't have reliable information about that feature."
    """
    async def _run():
        product_service.set_provider_mode("channel3")
        product_service.channel3_service.api_key = "test_c3_secret_key"

        mock_client = _mock_httpx_post_success()
        with patch("httpx.AsyncClient", return_value=mock_client):
            await ai_service.process_user_intent("Find wireless headphones under $80.")
            res_water = await ai_service.process_user_intent("Is it waterproof?")
            res_weight = await ai_service.process_user_intent("Which one is lightest?")

        assert res_water["action"] == "ATTRIBUTE_INQUIRY"
        assert res_water["found"] is False
        assert res_water["message"] == "I don't have reliable information about that feature."

        assert res_weight["action"] == "ATTRIBUTE_INQUIRY"
        assert res_weight["found"] is False
        assert res_weight["message"] == "I don't have reliable information about that feature."

    asyncio.run(_run())


def test_followup_search_and_context_preservation():
    """
    Tests follow-up commands using cached Channel3 session data:
    - 'Only show ones under $50.'
    - 'Show another option.'
    - 'Tell me about the second one.'
    """
    async def _run():
        product_service.set_provider_mode("channel3")
        product_service.channel3_service.api_key = "test_c3_secret_key"

        mock_client = _mock_httpx_post_success()
        with patch("httpx.AsyncClient", return_value=mock_client):
            await ai_service.process_user_intent("Find wireless headphones under $80.")
            assert product_service.channel3_service.api_call_count == 1

            # Follow-up filter under $50 uses cached candidates without new API call
            r_under_50 = await ai_service.process_user_intent("Only show ones under $50.")
            assert r_under_50["action"] == "SEARCH_RESULTS"
            assert all(p["price"] <= 50.0 for p in r_under_50["products"])
            assert product_service.channel3_service.api_call_count == 1

            # 'Tell me about the second one' uses cached results
            r_details = await ai_service.process_user_intent("Tell me about the second one.")
            assert r_details["action"] == "PRODUCT_DETAILS"
            assert product_service.channel3_service.api_call_count == 1

            # 'Show another option' uses cached candidates
            r_another = await ai_service.process_user_intent("Show another option.")
            assert r_another["action"] == "SEARCH_RESULTS"
            assert product_service.channel3_service.api_call_count == 1

    asyncio.run(_run())


def test_security_channel3_key_never_in_frontend():
    """Verify CHANNEL3_API_KEY is never referenced or exposed in frontend code."""
    frontend_src = Path(__file__).resolve().parent.parent.parent / "frontend" / "src"
    for path in frontend_src.rglob("*"):
        if path.is_file():
            content = path.read_text(encoding="utf-8", errors="ignore")
            assert "CHANNEL3_API_KEY" not in content
            assert "x-api-key" not in content.lower()

