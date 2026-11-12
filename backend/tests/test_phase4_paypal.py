import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.models.purchase import PurchaseState
from app.services.ai_service import ai_service
from app.services.product_service import product_service
from app.services.cart_service import cart_service
from app.services.confirmation_service import confirmation_service
from app.services.accessibility_service import accessibility_service
from app.services.payment_service import (
    payment_service,
    PayPalPaymentService,
    MockPaymentService,
    SAFE_PAYMENT_FAILURE_MESSAGE,
    SANDBOX_BASE_URL,
)
from app.services.order_service import order_service
from app.api.payments import (
    create_paypal_sandbox_order,
    capture_paypal_sandbox_order,
    get_public_paypal_config,
    CreatePayPalOrderRequest,
    CapturePayPalOrderRequest,
)
from app.db.seed_data import seed_database
from app.db.database import db


@pytest.fixture(autouse=True)
def reset_phase4_state():
    orig_gemini = ai_service.llm_service.gemini_key
    orig_openai = ai_service.llm_service.openai_key
    ai_service.llm_service.gemini_key = ""
    ai_service.llm_service.openai_key = ""
    product_service.set_provider_mode("mock")
    seed_database()
    cart_service.clear()
    confirmation_service.reset()
    accessibility_service.reset_to_defaults()
    payment_service.reset_idempotency_state()
    payment_service.set_provider("auto")
    ai_service.reset_conversation()
    yield
    ai_service.llm_service.gemini_key = orig_gemini
    ai_service.llm_service.openai_key = orig_openai
    product_service.set_provider_mode(None)
    payment_service.reset_idempotency_state()
    payment_service.set_provider("auto")


def test_scenario_1_search_and_select_never_charges():
    """
    TEST SCENARIO 1:
    Search: 'Find wireless headphones under $80.'
    Select product.
    Verify: NO payment occurs.
    """
    async def _run():
        initial_orders = len(order_service.get_all_orders())
        search_res = await ai_service.process_user_intent("Find wireless headphones under $80.")
        assert search_res["action"] == "SEARCH_RESULTS"
        assert len(search_res["products"]) == 3

        select_res = await ai_service.process_user_intent("Choose the first one.")
        assert select_res["action"] == "PRODUCT_SELECTED"
        assert "No payment has been made" in select_res["message"]
        assert confirmation_service.get_state() not in [
            PurchaseState.PAYMENT_PROCESSING,
            PurchaseState.PAYMENT_COMPLETE,
        ]
        assert len(order_service.get_all_orders()) == initial_orders

    asyncio.run(_run())


def test_scenario_2_that_one_looks_good_never_charges():
    """
    TEST SCENARIO 2:
    Say: 'That one looks good.'
    Verify: NO payment occurs.
    """
    async def _run():
        cart_service.add_item("prod_headphone_sony", quantity=1)
        confirmation_service.prepare_payment_review()

        for phrase in ["That one looks good.", "I want that.", "Get it.", "Looks good."]:
            res = await ai_service.process_user_intent(phrase)
            assert res["action"] == "AMBIGUITY_GUARD"
            assert res.get("is_ambiguous") is True
            assert confirmation_service.is_confirmation_granted() is False
            assert confirmation_service.get_state() != PurchaseState.PAYMENT_COMPLETE

    asyncio.run(_run())


def test_scenario_3_yes_rejected_when_exact_confirmation_required():
    """
    TEST SCENARIO 3:
    Purchase total: $59.36
    Say: 'Yes.'
    Verify: NO payment occurs if exact confirmation is required.
    """
    async def _run():
        cart_service.add_item("prod_headphone_sony", quantity=1)
        review = confirmation_service.prepare_payment_review()
        assert review.total_today == 59.36
        assert review.requires_exact_phrase is True

        for bad_phrase in ["Yes.", "Okay.", "Buy it.", "Go ahead."]:
            res = await ai_service.process_user_intent(bad_phrase)
            assert res.get("success") is not True
            assert confirmation_service.is_confirmation_granted() is False

        # Attempt to create PayPal order without valid confirmation must be rejected
        order_attempt = await create_paypal_sandbox_order(
            CreatePayPalOrderRequest(review_token=review.review_token)
        )
        assert order_attempt["success"] is False

    asyncio.run(_run())


def test_scenario_4_and_5_confirm_create_order_and_capture_end_to_end():
    """
    TEST SCENARIO 4 & 5:
    Say: 'Confirm $59.36 purchase.'
    Verify:
    - AccessPay confirmation succeeds.
    - PayPal Sandbox checkout begins (server-controlled create-order).
    - Complete PayPal Sandbox buyer approval (capture-order).
    - Order is captured, purchase history is updated with all fields, and success response returned.
    """
    async def _run():
        initial_orders_count = len(order_service.get_all_orders())
        cart_service.add_item("prod_headphone_sony", quantity=1)
        review = confirmation_service.prepare_payment_review()
        assert review.total_today == 59.36

        # Step 1: Say "Confirm $59.36 purchase."
        ai_res = await ai_service.process_user_intent("Confirm $59.36 purchase.")
        assert ai_res["action"] == "PAYMENT_CONFIRMED"
        assert ai_res["success"] is True
        assert ai_res["state"] == PurchaseState.PAYMENT_PROCESSING
        assert confirmation_service.is_confirmation_granted() is True

        # Step 2: Create server-controlled PayPal Sandbox order
        create_res = await create_paypal_sandbox_order(
            CreatePayPalOrderRequest(review_token=review.review_token)
        )
        assert create_res["success"] is True
        assert create_res["amount"] == 59.36
        assert create_res["item_subtotal"] == 49.99
        assert create_res["shipping"] == 5.00
        assert create_res["tax"] == 4.37
        assert create_res["environment"] == "sandbox"
        paypal_order_id = create_res["paypal_order_id"]
        assert paypal_order_id is not None

        # Step 3: Complete PayPal Sandbox buyer approval -> Capture order
        capture_res = await capture_paypal_sandbox_order(
            paypal_order_id,
            CapturePayPalOrderRequest(
                review_token=review.review_token,
                interaction_mode="VOICE",
                confirmation_method="VOICE",
            ),
        )
        assert capture_res["success"] is True
        assert capture_res["state"] == PurchaseState.PAYMENT_COMPLETE
        assert capture_res["message"] == "Payment successful"
        assert capture_res["paypal_order_id"] == paypal_order_id
        assert capture_res["paypal_capture_id"] is not None
        assert capture_res["amount_charged"] == 59.36
        assert capture_res["product_title"] == "Sony WH-CH520 Lightweight Wireless Headphones"

        # Step 4: Verify purchase history stored all required fields
        orders = order_service.get_all_orders()
        assert len(orders) == initial_orders_count + 1
        latest = next(o for o in orders if o.paypal_order_id == paypal_order_id)
        assert latest.product_title == "Sony WH-CH520 Lightweight Wireless Headphones"
        assert latest.merchant == "AudioDirect Store"
        assert latest.item_price == 49.99
        assert latest.shipping == 5.00
        assert latest.tax == 4.37
        assert latest.total == 59.36
        assert latest.interaction_mode == "VOICE"
        assert "VOICE" in latest.confirmation_method
        assert latest.paypal_order_id == paypal_order_id
        assert latest.paypal_capture_id == capture_res["paypal_capture_id"]
        assert latest.payment_status == "PAID"
        assert latest.timestamp is not None

    asyncio.run(_run())


def test_scenario_6_cancel_before_paypal_payment():
    """
    TEST SCENARIO 6:
    Cancel before PayPal payment.
    Verify: No payment occurs and 'Purchase cancelled.\\n\\nNo payment was made.' is returned.
    """
    async def _run():
        initial_orders_count = len(order_service.get_all_orders())
        cart_service.add_item("prod_headphone_sony", quantity=1)
        review = confirmation_service.prepare_payment_review()

        # User confirms in AccessPay, creating PayPal order, then cancels before capture
        confirmation_service.validate_confirmation(
            token=review.review_token,
            spoken_phrase="Confirm $59.36 purchase",
            confirmation_method="VOICE",
        )
        create_res = await create_paypal_sandbox_order(
            CreatePayPalOrderRequest(review_token=review.review_token)
        )
        assert create_res["success"] is True

        # Cancel before capture
        cancel_res = confirmation_service.cancel_purchase("User cancelled on PayPal screen")
        assert cancel_res.success is True
        assert cancel_res.state == PurchaseState.CANCELLED
        assert "Purchase cancelled" in cancel_res.message
        assert "No payment was made" in cancel_res.message
        assert len(order_service.get_all_orders()) == initial_orders_count

    asyncio.run(_run())


def test_scenario_7_payment_failure_never_exposes_raw_paypal_errors():
    """
    TEST SCENARIO 7:
    Trigger payment failure (both simulated gateway decline and raw UNPROCESSABLE_ENTITY from PayPal API).
    Verify: Accessible failure message, no raw PayPal error exposed.
    """
    async def _run():
        cart_service.add_item("prod_headphone_sony", quantity=1)
        review = confirmation_service.prepare_payment_review()
        confirmation_service.validate_confirmation(
            token=review.review_token,
            spoken_phrase="Confirm $59.36 purchase",
            confirmation_method="VOICE",
        )

        # 1. Test raw PayPal UNPROCESSABLE_ENTITY response translation
        service = PayPalPaymentService()
        service.client_id = "sbx_client_id"
        service.client_secret = "sbx_client_secret"

        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {"access_token": "mock_sandbox_token"}

        mock_fail_resp = MagicMock()
        mock_fail_resp.status_code = 422
        mock_fail_resp.text = '{"name":"UNPROCESSABLE_ENTITY","details":[{"issue":"INSTRUMENT_DECLINED"}]}'

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = [mock_token_resp, mock_fail_resp]
            cap_res = await service.capture_order("ORDER-422-TEST")
            assert cap_res["success"] is False
            assert cap_res["user_message"] == SAFE_PAYMENT_FAILURE_MESSAGE
            assert "UNPROCESSABLE_ENTITY" not in cap_res["user_message"]
            assert "INSTRUMENT_DECLINED" not in cap_res["user_message"]

        # 2. Test endpoint failure response via simulated gateway failure
        payment_service.set_simulate_failure(True)
        order_fail = await create_paypal_sandbox_order(
            CreatePayPalOrderRequest(review_token=review.review_token)
        )
        assert order_fail["success"] is False
        assert order_fail["message"] == SAFE_PAYMENT_FAILURE_MESSAGE
        assert "UNPROCESSABLE_ENTITY" not in order_fail["message"]

    asyncio.run(_run())


def test_scenario_8_duplicate_submit_and_idempotency_protection():
    """
    TEST SCENARIO 8:
    Rapidly click/activate Confirm or call create-order / capture-order multiple times.
    Verify: Only one payment flow/order/capture is created.
    """
    async def _run():
        cart_service.add_item("prod_headphone_sony", quantity=1)
        review = confirmation_service.prepare_payment_review()

        # First confirmation succeeds
        res1 = confirmation_service.validate_confirmation(
            token=review.review_token,
            spoken_phrase="Confirm $59.36 purchase",
            confirmation_method="VOICE",
        )
        assert res1.success is True

        # Second rapid confirmation while processing is blocked
        res2 = confirmation_service.validate_confirmation(
            token=review.review_token,
            spoken_phrase="Confirm $59.36 purchase",
            confirmation_method="VOICE",
        )
        assert res2.success is False
        assert "Duplicate payment prevented" in res2.message

        # Calling create-order multiple times with same review_token returns the same idempotent order ID
        order1 = await create_paypal_sandbox_order(
            CreatePayPalOrderRequest(review_token=review.review_token)
        )
        order2 = await create_paypal_sandbox_order(
            CreatePayPalOrderRequest(review_token=review.review_token)
        )
        assert order1["success"] is True
        assert order2["success"] is True
        assert order1["paypal_order_id"] == order2["paypal_order_id"]

        # Capturing the same order a second time is blocked
        cap1 = await payment_service.capture_order(order1["paypal_order_id"])
        cap2 = await payment_service.capture_order(order1["paypal_order_id"])
        assert cap1["success"] is True
        assert cap2["success"] is False
        assert cap2.get("already_captured") is True

    asyncio.run(_run())


def test_scenario_9_price_and_total_change_protection():
    """
    TEST SCENARIO 9:
    Change price, shipping, tax, or quantity after initial review.
    Verify: Previous confirmation is invalidated and create-order stops immediately.
    """
    async def _run():
        cart_service.add_item("prod_keyboard_logitech", quantity=1)
        review = confirmation_service.prepare_payment_review()
        assert review.item_subtotal == 54.99

        # Confirm at $54.99 item price
        c_res = confirmation_service.validate_confirmation(
            token=review.review_token,
            spoken_phrase=review.expected_phrase,
            confirmation_method="VOICE",
        )
        assert c_res.success is True

        # Price changes from $54.99 to $62.99 before PayPal order creation
        confirmation_service.simulate_price_change(62.99)

        # Attempting to create PayPal order must STOP and report the price change
        create_res = await create_paypal_sandbox_order(
            CreatePayPalOrderRequest(review_token=review.review_token)
        )
        assert create_res["success"] is False
        assert create_res.get("price_changed") is True
        assert "The price changed from $54.99 to $62.99." in create_res["message"]
        assert "Please review the updated total." in create_res["message"]
        assert confirmation_service.is_confirmation_granted() is False

        # Also test quantity change invalidation on a fresh review
        cart_service.clear()
        cart_service.add_item("prod_headphone_sony", quantity=1)
        review2 = confirmation_service.prepare_payment_review()
        confirmation_service.validate_confirmation(
            token=review2.review_token,
            spoken_phrase=review2.expected_phrase,
            confirmation_method="LARGE_CONTROLS",
        )
        # User or external action changes quantity from 1 to 2
        cart_service.update_quantity("prod_headphone_sony", 2)
        create_res2 = await create_paypal_sandbox_order(
            CreatePayPalOrderRequest(review_token=review2.review_token)
        )
        assert create_res2["success"] is False
        assert create_res2.get("price_changed") is True
        assert "quantity changed" in create_res2["message"].lower()

    asyncio.run(_run())


def test_scenario_10_all_four_accessibility_modes_payment():
    """
    TEST SCENARIO 10:
    Test payment using Voice, Large Controls, Keyboard, and Switch-Compatible modes.
    """
    async def _run():
        modes = ["VOICE", "LARGE_CONTROLS", "KEYBOARD", "SWITCH"]
        for mode in modes:
            cart_service.clear()
            confirmation_service.reset()
            payment_service.reset_idempotency_state()

            accessibility_service.set_mode(mode)
            cart_service.add_item("prod_headphone_anker", quantity=1)
            review = confirmation_service.prepare_payment_review()

            spoken = review.expected_phrase if mode == "VOICE" else f"CONFIRM ${review.total_today:.2f}"
            val = confirmation_service.validate_confirmation(
                token=review.review_token,
                spoken_phrase=spoken,
                confirmation_method=mode,
            )
            assert val.success is True

            order_res = await create_paypal_sandbox_order(
                CreatePayPalOrderRequest(review_token=review.review_token)
            )
            assert order_res["success"] is True

            cap_res = await capture_paypal_sandbox_order(
                order_res["paypal_order_id"],
                CapturePayPalOrderRequest(
                    review_token=review.review_token,
                    interaction_mode=mode,
                    confirmation_method=mode,
                ),
            )
            assert cap_res["success"] is True
            assert cap_res["state"] == PurchaseState.PAYMENT_COMPLETE

    asyncio.run(_run())


def test_paypal_sandbox_orders_v2_wire_protocol_and_security():
    """
    Verifies:
    1. Official PayPal Orders v2 API wire format (OAuth2 + create order with breakdown + capture).
    2. Strict Sandbox URL enforcement (never live).
    3. PAYPAL_CLIENT_SECRET is never exposed in public config or frontend code.
    """
    async def _run():
        service = PayPalPaymentService()
        service.client_id = "test_sandbox_client_id"
        service.client_secret = "test_sandbox_secret_DO_NOT_LEAK"
        assert service.base_url == SANDBOX_BASE_URL
        assert "sandbox.paypal.com" in service.base_url

        cart_service.add_item("prod_headphone_sony", quantity=1)
        cart = cart_service.get_cart()

        mock_oauth = MagicMock()
        mock_oauth.status_code = 200
        mock_oauth.json.return_value = {"access_token": "sbx_access_token_123"}

        mock_create = MagicMock()
        mock_create.status_code = 201
        mock_create.json.return_value = {
            "id": "5O190127TN364715T",
            "status": "CREATED",
            "links": [
                {"href": "https://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T", "rel": "approve", "method": "GET"}
            ],
        }

        mock_capture = MagicMock()
        mock_capture.status_code = 201
        mock_capture.json.return_value = {
            "id": "5O190127TN364715T",
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "payments": {
                        "captures": [
                            {"id": "2GG903537H418764H", "status": "COMPLETED"}
                        ]
                    }
                }
            ],
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = [mock_oauth, mock_create, mock_oauth, mock_capture]

            create_res = await service.create_order(
                amount=cart.total_today,
                currency="USD",
                description="Sony WH-CH520 Wireless Headphones",
                cart=cart,
                idempotency_key="rev_test_123",
            )
            assert create_res["success"] is True
            assert create_res["paypal_order_id"] == "5O190127TN364715T"
            assert create_res["environment"] == "sandbox"
            assert "sandbox.paypal.com" in create_res["approval_url"]

            # Verify create_order request payload had itemized breakdown & PayPal-Request-Id
            create_call = mock_post.call_args_list[1]
            assert create_call.args[0] == "https://api-m.sandbox.paypal.com/v2/checkout/orders"
            assert create_call.kwargs["headers"]["PayPal-Request-Id"] == "rev_test_123"
            sent_unit = create_call.kwargs["json"]["purchase_units"][0]
            assert sent_unit["amount"]["value"] == "59.36"
            assert sent_unit["amount"]["breakdown"]["item_total"]["value"] == "49.99"
            assert sent_unit["amount"]["breakdown"]["shipping"]["value"] == "5.00"
            assert sent_unit["amount"]["breakdown"]["tax_total"]["value"] == "4.37"

            cap_res = await service.capture_order("5O190127TN364715T", idempotency_key="cap_test_123")
            assert cap_res["success"] is True
            assert cap_res["paypal_order_id"] == "5O190127TN364715T"
            assert cap_res["paypal_capture_id"] == "2GG903537H418764H"
            assert cap_res["status"] == "COMPLETED"

        # Verify public config never exposes PAYPAL_CLIENT_SECRET
        pub_cfg = get_public_paypal_config()
        assert "PAYPAL_CLIENT_SECRET" not in str(pub_cfg)
        assert "client_secret" not in pub_cfg
        assert pub_cfg["environment"] == "sandbox"

        # Verify frontend source never references PAYPAL_CLIENT_SECRET
        frontend_src = Path(__file__).resolve().parent.parent.parent / "frontend" / "src"
        for src_file in frontend_src.rglob("*"):
            if src_file.is_file():
                content = src_file.read_text(encoding="utf-8", errors="ignore")
                assert "PAYPAL_CLIENT_SECRET" not in content

    asyncio.run(_run())


def test_paypal_approval_sequence_status_and_return_urls():
    """
    Verifies CREATE -> APPROVE -> CAPTURE sequence enforcement:
    - create_order forwards validated return_url and cancel_url
    - capturing unapproved order (HTTP 422 ORDER_NOT_APPROVED) fails safely without updating history
    - get_order_status inspects CREATED / APPROVED / COMPLETED states cleanly
    """
    async def _run():
        service = PayPalPaymentService()
        service.client_id = "sbx_client_id"
        service.client_secret = "sbx_client_secret"

        mock_oauth = MagicMock()
        mock_oauth.status_code = 200
        mock_oauth.json.return_value = {"access_token": "sbx_token"}

        mock_create = MagicMock()
        mock_create.status_code = 201
        mock_create.json.return_value = {
            "id": "9AP1234567890123X",
            "status": "CREATED",
            "links": [{"href": "https://www.sandbox.paypal.com/checkoutnow?token=9AP1234567890123X", "rel": "approve"}],
        }

        mock_status_approved = MagicMock()
        mock_status_approved.status_code = 200
        mock_status_approved.json.return_value = {
            "id": "9AP1234567890123X",
            "status": "APPROVED",
            "purchase_units": [{"amount": {"currency_code": "USD", "value": "15.11"}}],
        }

        mock_unapproved = MagicMock()
        mock_unapproved.status_code = 422
        mock_unapproved.json.return_value = {
            "name": "UNPROCESSABLE_ENTITY",
            "details": [{"issue": "ORDER_NOT_APPROVED", "description": "Payer has not yet approved the Order"}],
            "debug_id": "dbg_422_unapproved",
        }

        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        ):
            mock_post.side_effect = [mock_oauth, mock_create, mock_oauth, mock_unapproved]
            mock_get.return_value = mock_status_approved

            create_res = await service.create_order(
                amount=15.11,
                currency="USD",
                description="Classic Water Bottle",
                return_url="http://127.0.0.1:5173/?paypal_return=1",
                cancel_url="http://127.0.0.1:5173/?paypal_cancel=1",
            )
            assert create_res["success"] is True
            sent_app_ctx = mock_post.call_args_list[1].kwargs["json"]["application_context"]
            assert sent_app_ctx["return_url"] == "http://127.0.0.1:5173/?paypal_return=1"
            assert sent_app_ctx["cancel_url"] == "http://127.0.0.1:5173/?paypal_cancel=1"

            # Unapproved capture must fail safely
            unapproved_cap = await service.capture_order("9AP1234567890123X")
            assert unapproved_cap["success"] is False
            assert unapproved_cap["error"] == "PAYPAL_CAPTURE_HTTP_422"
            assert unapproved_cap["user_message"] == SAFE_PAYMENT_FAILURE_MESSAGE

            # Check order status inspection after buyer approval
            mock_post.side_effect = [mock_oauth]
            status_res = await service.get_order_status("9AP1234567890123X")
            assert status_res["success"] is True
            assert status_res["status"] == "APPROVED"
            assert status_res["amount"] == 15.11

    asyncio.run(_run())
