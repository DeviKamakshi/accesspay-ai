import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.models.product import Product
from app.models.purchase import PurchaseState
from app.services.ai_service import ai_service
from app.services.product_service import product_service
from app.services.cart_service import cart_service
from app.services.confirmation_service import confirmation_service
from app.services.accessibility_service import accessibility_service
from app.services.payment_service import (
    payment_service,
    PayPalPaymentService,
    build_paypal_purchase_unit,
)
from app.services.order_service import order_service
from app.api.payments import (
    create_paypal_sandbox_order,
    capture_paypal_sandbox_order,
    CreatePayPalOrderRequest,
    CapturePayPalOrderRequest,
)
from app.db.seed_data import seed_database


@pytest.fixture(autouse=True)
def reset_multi_item_state():
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
    for pid in ("test_decimal_a", "test_decimal_b", "test_decimal_c"):
        product_service.channel3_service.cached_by_id.pop(pid, None)
    cart_service.clear()
    confirmation_service.reset()
    ai_service.llm_service.gemini_key = orig_gemini
    ai_service.llm_service.openai_key = orig_openai
    product_service.set_provider_mode(None)
    payment_service.reset_idempotency_state()
    payment_service.set_provider("auto")


def _register_test_products():
    p_a = Product(
        id="test_decimal_a",
        title="Canvas Backpack",
        price=19.99,
        merchant="GearHub",
        category="Bags",
        shipping=5.00,
        estimated_tax=1.59,
    )
    p_b = Product(
        id="test_decimal_b",
        title="Insulated Bottle",
        price=7.49,
        merchant="HydroCo",
        category="Drinkware",
        shipping=0.00,
        estimated_tax=0.60,
    )
    p_c = Product(
        id="test_decimal_c",
        title="USB-C Braided Cable",
        price=12.45,
        merchant="CablePro",
        category="Electronics",
        shipping=2.50,
        estimated_tax=1.00,
    )
    for prod in (p_a, p_b, p_c):
        product_service.channel3_service.cached_by_id[prod.id] = prod
    return p_a, p_b, p_c


def test_decimal_rounding_and_paypal_breakdown_precision():
    """Verify $19.99 x 3 + $7.49 x 2 computes exact cent totals and exact PayPal breakdown."""
    _register_test_products()

    cart_service.add_item("test_decimal_a", quantity=3)
    cart = cart_service.add_item("test_decimal_b", quantity=2)

    assert len(cart.items) == 2
    assert cart.item_count == 5
    # 19.99*3 = 59.97, 7.49*2 = 14.98 => 74.95
    assert cart.items[0].item_total == 59.97
    assert cart.items[1].item_total == 14.98
    assert cart.subtotal == 74.95
    # Shipping: 5.00 + 0.00 = 5.00
    assert cart.shipping_total == 5.00
    # Tax: 1.59*3 (4.77) + 0.60*2 (1.20) = 5.97
    assert cart.tax_total == 5.97
    # Total: 74.95 + 5.00 + 5.97 = 85.92
    assert cart.total_today == 85.92

    # Adding same product again increments quantity and recalculates line_total without overwriting
    cart_inc = cart_service.add_item("test_decimal_a", quantity=1)
    assert cart_inc.items[0].quantity == 4
    assert cart_inc.items[0].item_total == 79.96
    assert cart_inc.subtotal == 94.94

    # Check PayPal v2 purchase_unit reconciliation across all items
    pu = build_paypal_purchase_unit(
        amount=cart_inc.total_today,
        currency="USD",
        description="Multi-item test",
        cart=cart_inc,
    )
    assert pu["amount"]["value"] == f"{cart_inc.total_today:.2f}"
    bd = pu["amount"]["breakdown"]
    assert bd["item_total"]["value"] == "94.94"
    assert bd["shipping"]["value"] == f"{cart_inc.shipping_total:.2f}"
    assert bd["tax_total"]["value"] == f"{cart_inc.tax_total:.2f}"
    assert len(pu["items"]) == 2
    assert Decimal(bd["item_total"]["value"]) + Decimal(bd["shipping"]["value"]) + Decimal(bd["tax_total"]["value"]) == Decimal(pu["amount"]["value"])


def test_single_item_regression_end_to_end():
    """Single-item purchase continues working end-to-end across Review, PayPal, Receipt, and Orders."""
    _register_test_products()

    async def _run():
        cart = cart_service.add_item("test_decimal_a", quantity=1)
        expected_total = cart.total_today  # 19.99 + 5.00 + 1.59 = 26.58
        assert expected_total == 26.58

        review = confirmation_service.prepare_payment_review()
        assert review.total_today == expected_total
        assert review.expected_phrase == "Confirm $26.58 purchase"

        c_res = confirmation_service.validate_confirmation(
            token=review.review_token,
            spoken_phrase=review.expected_phrase,
            confirmation_method="VOICE",
        )
        assert c_res.success is True

        create_res = await create_paypal_sandbox_order(
            CreatePayPalOrderRequest(review_token=review.review_token)
        )
        assert create_res["success"] is True
        assert create_res["amount"] == 26.58
        assert len(create_res["items"]) == 1
        assert create_res["items"][0]["line_total"] == 19.99

        cap_res = await capture_paypal_sandbox_order(
            order_id=create_res["paypal_order_id"],
            req=CapturePayPalOrderRequest(confirmation_method="VOICE"),
        )
        assert cap_res["success"] is True
        assert cap_res["amount_charged"] == 26.58
        assert len(cap_res["items"]) == 1

        orders = order_service.get_all_orders()
        saved = orders[0]
        assert saved.order_id == cap_res["order_id"]
        assert saved.total == 26.58
        assert len(saved.items) == 1
        assert saved.items[0].product_title == "Canvas Backpack"

    asyncio.run(_run())


def test_multi_item_three_products_paypal_wire_receipt_and_history():
    """
    3 distinct products end-to-end:
    Cart == Review == Confirmation == PayPal Sandbox Wire Payload == Capture == Receipt == OrderRecord history.
    """
    _register_test_products()

    async def _run():
        cart_service.add_item("test_decimal_a", quantity=2, variant={"color": "Navy"})
        cart_service.add_item("test_decimal_b", quantity=1)
        cart = cart_service.add_item("test_decimal_c", quantity=3)

        # Subtotal: 19.99*2 (39.98) + 7.49*1 (7.49) + 12.45*3 (37.35) = 84.82
        # Shipping: 5.00 + 0.00 + 2.50 = 7.50
        # Tax: 1.59*2 (3.18) + 0.60*1 (0.60) + 1.00*3 (3.00) = 6.78
        # Total: 84.82 + 7.50 + 6.78 = 99.10
        assert cart.item_count == 6
        assert cart.subtotal == 84.82
        assert cart.shipping_total == 7.50
        assert cart.tax_total == 6.78
        assert cart.total_today == 99.10

        review = confirmation_service.prepare_payment_review()
        assert review.total_today == 99.10
        assert review.expected_phrase == "Confirm $99.10 purchase"
        assert len(review.cart.items) == 3

        conf_res = confirmation_service.validate_confirmation(
            token=review.review_token,
            spoken_phrase="Confirm $99.10 purchase",
            confirmation_method="LARGE_CONTROLS",
        )
        assert conf_res.success is True

        captured_wire_payloads = []
        live_pp = PayPalPaymentService()
        live_pp.client_id = "test_client_id"
        live_pp.client_secret = "test_client_secret"
        live_pp.get_access_token = AsyncMock(return_value="PP_SANDBOX_TOKEN")

        mock_create_resp = MagicMock()
        mock_create_resp.status_code = 201
        mock_create_resp.json.return_value = {
            "id": "PAYPAL-MULTI-ORDER-9910",
            "status": "CREATED",
            "links": [{"rel": "approve", "href": "https://www.sandbox.paypal.com/checkoutnow?token=PAYPAL-MULTI-ORDER-9910"}],
        }

        mock_order_status_resp = MagicMock()
        mock_order_status_resp.status_code = 200
        mock_order_status_resp.json.return_value = {
            "id": "PAYPAL-MULTI-ORDER-9910",
            "status": "APPROVED",
            "purchase_units": [{"amount": {"currency_code": "USD", "value": "99.10"}}],
        }

        mock_capture_resp = MagicMock()
        mock_capture_resp.status_code = 201
        mock_capture_resp.json.return_value = {
            "id": "PAYPAL-MULTI-ORDER-9910",
            "status": "COMPLETED",
            "purchase_units": [{"payments": {"captures": [{"id": "CAP-MULTI-9910", "status": "COMPLETED"}]}}],
        }

        async def mock_post(url, json=None, headers=None, **kwargs):
            if url.endswith("/v2/checkout/orders"):
                captured_wire_payloads.append(json)
                return mock_create_resp
            return mock_capture_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=mock_post)
        mock_client.get = AsyncMock(return_value=mock_order_status_resp)

        with patch.object(payment_service, "paypal_service", live_pp), \
             patch.object(payment_service, "provider_config", "paypal"), \
             patch("app.services.payment_service.httpx.AsyncClient", return_value=mock_client):
            create_res = await create_paypal_sandbox_order(
                CreatePayPalOrderRequest(review_token=review.review_token)
            )
            assert create_res["success"] is True
            assert create_res["paypal_order_id"] == "PAYPAL-MULTI-ORDER-9910"
            assert create_res["amount"] == 99.10
            assert create_res["item_subtotal"] == 84.82
            assert create_res["shipping"] == 7.50
            assert create_res["tax"] == 6.78
            assert len(create_res["items"]) == 3

            # Inspect exact PayPal Sandbox Orders v2 wire payload
            assert len(captured_wire_payloads) == 1
            wire_pu = captured_wire_payloads[0]["purchase_units"][0]
            assert wire_pu["amount"]["value"] == "99.10"
            assert wire_pu["amount"]["breakdown"]["item_total"]["value"] == "84.82"
            assert wire_pu["amount"]["breakdown"]["shipping"]["value"] == "7.50"
            assert wire_pu["amount"]["breakdown"]["tax_total"]["value"] == "6.78"
            assert len(wire_pu["items"]) == 3
            assert [(it["name"], it["quantity"], it["unit_amount"]["value"]) for it in wire_pu["items"]] == [
                ("Canvas Backpack", "2", "19.99"),
                ("Insulated Bottle", "1", "7.49"),
                ("USB-C Braided Cable", "3", "12.45"),
            ]

            cap_res = await capture_paypal_sandbox_order(
                order_id="PAYPAL-MULTI-ORDER-9910",
                req=CapturePayPalOrderRequest(confirmation_method="LARGE_CONTROLS"),
            )
            assert cap_res["success"] is True
            assert cap_res["paypal_order_id"] == "PAYPAL-MULTI-ORDER-9910"
            assert cap_res["paypal_capture_id"] == "CAP-MULTI-9910"
            assert cap_res["amount_charged"] == 99.10
            assert cap_res["item_subtotal"] == 84.82
            assert cap_res["shipping"] == 7.50
            assert cap_res["tax"] == 6.78
            assert len(cap_res["items"]) == 3

        # Verify authoritative purchase history record persists all 3 line items
        saved = order_service.get_all_orders()[0]
        assert saved.paypal_order_id == "PAYPAL-MULTI-ORDER-9910"
        assert saved.paypal_capture_id == "CAP-MULTI-9910"
        assert saved.total == 99.10
        assert saved.item_subtotal == 84.82
        assert saved.shipping == 7.50
        assert saved.tax == 6.78
        assert saved.quantity == 6
        assert len(saved.items) == 3
        assert [(li.product_title, li.quantity, li.unit_price, li.line_total) for li in saved.items] == [
            ("Canvas Backpack", 2, 19.99, 39.98),
            ("Insulated Bottle", 1, 7.49, 7.49),
            ("USB-C Braided Cable", 3, 12.45, 37.35),
        ]

    asyncio.run(_run())


def test_cart_mutations_invalidate_confirmation_and_require_rereview():
    """Adding, removing, or updating cart quantity invalidates prior confirmation."""
    _register_test_products()

    async def _run():
        # 1. Confirm single item
        cart_service.add_item("test_decimal_a", quantity=1)
        rev1 = confirmation_service.prepare_payment_review()
        assert confirmation_service.validate_confirmation(rev1.review_token, rev1.expected_phrase, "VOICE").success is True
        assert confirmation_service.is_confirmation_granted() is True

        # Add a second product -> must invalidate confirmation immediately
        cart_service.add_item("test_decimal_b", quantity=1)
        assert confirmation_service.is_confirmation_granted() is False
        assert confirmation_service.get_active_review().is_invalidated is True

        # Old token cannot create PayPal order
        blocked = await create_paypal_sandbox_order(CreatePayPalOrderRequest(review_token=rev1.review_token))
        assert blocked["success"] is False

        # Re-review and confirm new total
        rev2 = confirmation_service.prepare_payment_review()
        assert rev2.review_token != rev1.review_token
        assert confirmation_service.validate_confirmation(rev2.review_token, rev2.expected_phrase, "VOICE").success is True

        # Update quantity -> must invalidate
        cart_service.update_quantity("test_decimal_b", 2)
        assert confirmation_service.is_confirmation_granted() is False

        # Re-review, confirm, then remove item -> must invalidate
        rev3 = confirmation_service.prepare_payment_review()
        assert confirmation_service.validate_confirmation(rev3.review_token, rev3.expected_phrase, "VOICE").success is True
        cart_service.remove_item("test_decimal_a")
        assert confirmation_service.is_confirmation_granted() is False

    asyncio.run(_run())


def test_whats_my_total_and_multi_item_chat_workflow():
    """'What's my total?' reports distinct products, total items, and complete cart total."""
    _register_test_products()

    async def _run():
        cart_service.add_item("test_decimal_a", quantity=2)
        cart_service.add_item("test_decimal_b", quantity=1)
        # Keep selected_product on product A only to verify CHECK_TOTAL never falls back to selectedProduct.price
        ai_service.mock_service.session.selected_product = product_service.get_product_by_id("test_decimal_a").model_dump()

        res_total = await ai_service.process_user_intent("What's my total?")
        assert res_total["action"] == "TOTAL_SUMMARY"
        assert "2 different products and 3 items in your cart" in res_total["message"]
        # 19.99*2 + 7.49 = 47.47 subtotal + 5.00 shipping + (1.59*2 + 0.60 = 3.78) tax = 56.25
        assert "Your total today is $56.25." in res_total["message"]
        assert res_total["cart"]["total_today"] == 56.25

        res_review = await ai_service.process_user_intent("Review purchase.")
        assert res_review["action"] == "PAYMENT_REVIEW_READY"
        assert "Canvas Backpack" in res_review["message"]
        assert "Insulated Bottle" in res_review["message"]
        assert "TOTAL: $56.25" in res_review["message"]

    asyncio.run(_run())
