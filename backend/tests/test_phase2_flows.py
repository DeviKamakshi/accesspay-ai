import pytest
import asyncio
from app.models.purchase import PurchaseState
from app.services.ai_service import ai_service
from app.services.product_service import product_service
from app.services.cart_service import cart_service
from app.services.confirmation_service import confirmation_service
from app.services.accessibility_service import accessibility_service
from app.db.seed_data import seed_database


@pytest.fixture(autouse=True)
def setup_state():
    orig_gemini = ai_service.llm_service.gemini_key
    orig_openai = ai_service.llm_service.openai_key
    ai_service.llm_service.gemini_key = ""
    ai_service.llm_service.openai_key = ""
    product_service.set_provider_mode("mock")
    seed_database()
    cart_service.clear()
    confirmation_service.reset()
    accessibility_service.reset_to_defaults()
    ai_service.reset_conversation()
    yield
    ai_service.llm_service.gemini_key = orig_gemini
    ai_service.llm_service.openai_key = orig_openai
    product_service.set_provider_mode(None)


def test_flow_1_find_wireless_headphones_under_80():
    """Flow 1: 'Find wireless headphones under $80.' -> Show approximately 3 products."""
    async def _run():
        res = await ai_service.process_user_intent("Find wireless headphones under $80.")
        assert res["action"] == "SEARCH_RESULTS"
        assert "products" in res
        assert len(res["products"]) == 3
        for p in res["products"]:
            assert p["price"] <= 80.0
    asyncio.run(_run())


def test_flow_2_compare_the_first_two():
    """Flow 2: 'Compare the first two.' -> Show a short comparison."""
    async def _run():
        await ai_service.process_user_intent("Find wireless headphones under $80.")
        res = await ai_service.process_user_intent("Compare the first two.")
        assert res["action"] == "COMPARE"
        assert "Option 1" in res["message"]
        assert "Option 2" in res["message"]
        assert "Recommendation:" in res["message"]
        assert "comparison" in res
    asyncio.run(_run())


def test_flow_3_show_something_cheaper():
    """Flow 3: 'Show something cheaper.' -> Show a cheaper alternative."""
    async def _run():
        await ai_service.process_user_intent("Find wireless headphones under $80.")
        res = await ai_service.process_user_intent("Show something cheaper.")
        assert res["action"] == "CHEAPER_ALTERNATIVE_FOUND"
        assert "savings" in res
        assert res["savings"] > 0
        assert res["alternative_product"]["price"] < res["original_product"]["price"]
    asyncio.run(_run())


def test_flow_4_choose_the_second_one_does_not_purchase():
    """Flow 4: 'Choose the second one.' -> Select it. Do NOT purchase."""
    async def _run():
        await ai_service.process_user_intent("Find wireless headphones under $80.")
        res = await ai_service.process_user_intent("Choose the second one.")
        assert res["action"] == "PRODUCT_SELECTED"
        assert res["product"]["title"] is not None
        assert confirmation_service.get_state() != PurchaseState.PAYMENT_COMPLETE
        assert confirmation_service.get_state() != PurchaseState.PAYMENT_PROCESSING
        cart = cart_service.get_cart()
        assert cart.item_count == 1
    asyncio.run(_run())


def test_flow_5_that_looks_good_does_not_purchase():
    """Flow 5: 'That looks good.' -> Do NOT purchase."""
    async def _run():
        await ai_service.process_user_intent("Find wireless headphones under $80.")
        await ai_service.process_user_intent("Choose the first one.")
        res = await ai_service.process_user_intent("That looks good.")
        assert res["action"] == "AMBIGUITY_GUARD"
        assert res.get("is_ambiguous") is True
        assert confirmation_service.get_state() != PurchaseState.PAYMENT_COMPLETE
    asyncio.run(_run())


def test_flow_6_purchase_review():
    """Flow 6: Show purchase review: Item, Shipping, Tax, Total."""
    cart_service.add_item("prod_headphone_sony", quantity=1)
    review = confirmation_service.prepare_payment_review()
    assert review.item_subtotal == 49.99
    assert review.shipping == 5.00
    assert review.tax == 4.37
    assert review.total_today == 59.36
    assert review.state == PurchaseState.PAYMENT_REVIEW
    assert confirmation_service.get_state() == PurchaseState.PAYMENT_REVIEW


def test_flow_7_all_four_accessibility_modes():
    """Flow 7: Test Voice, Large Controls, Keyboard, Switch modes."""
    for mode in ["VOICE", "LARGE_CONTROLS", "KEYBOARD", "SWITCH"]:
        updated = accessibility_service.set_mode(mode)
        assert updated.current_mode == mode


def test_flow_8_subscription_warning():
    """Flow 8: Test subscription warning: recurring payment terms clearly identified."""
    cart_service.add_item("prod_subscription_music", quantity=1)
    review = confirmation_service.prepare_payment_review()
    assert review.is_subscription is True
    assert review.subscription_terms is not None
    assert "$9.99" in review.subscription_terms
    assert "month" in review.subscription_terms


def test_flow_9_test_cancel():
    """Flow 9: Test cancel: 'Purchase cancelled. No payment was made.'"""
    async def _run():
        cart_service.add_item("prod_headphone_sony", quantity=1)
        confirmation_service.prepare_payment_review()
        res = await ai_service.process_user_intent("Cancel.")
        assert res["action"] == "CANCELLED"
        assert "Purchase cancelled" in res["message"]
        assert "No payment was made" in res["message"]
        assert confirmation_service.get_state() == PurchaseState.CANCELLED
        assert cart_service.get_cart().item_count == 0
    asyncio.run(_run())


def test_flow_10_ai_cannot_trigger_payment():
    """Flow 10: Verify AI cannot trigger payment without exact user authorization."""
    async def _run():
        cart_service.add_item("prod_headphone_sony", quantity=1)
        confirmation_service.prepare_payment_review()

        for phrase in ["Yes", "Okay", "Looks good", "Get it", "Authorize now", "Buy", "Order"]:
            res = await ai_service.process_user_intent(phrase)
            assert confirmation_service.get_state() != PurchaseState.PAYMENT_COMPLETE
            assert res.get("success") is not True
    asyncio.run(_run())


def test_natural_language_context_commands():
    """Verify additional voice/NL commands: cheaper selection, wireless filter, details, total, repeat, back."""
    async def _run():
        await ai_service.process_user_intent("Find headphones under $80.")
        r_details = await ai_service.process_user_intent("Tell me about the second one.")
        assert r_details["action"] == "PRODUCT_DETAILS"

        r_rec = await ai_service.process_user_intent("Which one is better for me?")
        assert r_rec["action"] == "RECOMMENDATION"

        r_cheap_pick = await ai_service.process_user_intent("Choose the cheaper one.")
        assert r_cheap_pick["action"] == "PRODUCT_SELECTED"
        assert r_cheap_pick["product"]["price"] == 39.99
        assert confirmation_service.get_state() != PurchaseState.PAYMENT_COMPLETE

        r_total = await ai_service.process_user_intent("What's my total?")
        assert r_total["action"] == "TOTAL_SUMMARY"

        r_repeat = await ai_service.process_user_intent("Repeat that.")
        assert r_repeat["action"] == "INFO"

        r_back = await ai_service.process_user_intent("Go back.")
        assert r_back["action"] == "NAVIGATE_BACK"
    asyncio.run(_run())
