from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.services.subscription_confirmation_service import SubscriptionConfirmationService
from app.services.subscription_provider import subscription_provider

client = TestClient(app)


def test_subscription_provider_demo_catalog_isolation():
    offers = subscription_provider.search("developer api")
    assert len(offers) >= 2
    for offer in offers:
        assert offer.is_demo is True
        assert offer.source == "demo_subscription_catalog"
        assert offer.recurring_amount > 0
        assert offer.billing_frequency in ("monthly", "yearly")

    yearly = subscription_provider.search("annual")
    assert yearly[0].billing_frequency == "yearly"


def test_subscription_confirmation_requires_exact_amount_and_frequency():
    svc = SubscriptionConfirmationService()
    offer = subscription_provider.get_offer("sub_dev_api_pro")
    assert offer is not None

    review = svc.prepare_review(offer)
    assert review.expected_phrase == "Confirm $19.99 monthly subscription"

    # Casual phrases must be rejected
    for phrase in ["Yes", "Okay", "Sure", "Go ahead", "Subscribe", "Confirm", "Click confirm"]:
        res = svc.confirm_subscription(review.review_token, phrase, "VOICE")
        assert res.success is False
        assert res.is_ambiguous is True
        assert svc.is_confirmation_granted(review.review_token) is False

    # Wrong amount must be rejected
    wrong_amt = svc.confirm_subscription(review.review_token, "Confirm $9.99 monthly subscription", "VOICE")
    assert wrong_amt.success is False
    assert wrong_amt.wrong_amount is True
    assert svc.is_confirmation_granted(review.review_token) is False

    # Wrong frequency must be rejected
    wrong_freq = svc.confirm_subscription(review.review_token, "Confirm $19.99 yearly subscription", "VOICE")
    assert wrong_freq.success is False
    assert wrong_freq.wrong_frequency is True
    assert svc.is_confirmation_granted(review.review_token) is False

    # Exact recurring amount + billing frequency passes
    ok = svc.confirm_subscription(review.review_token, "Confirm $19.99 monthly subscription", "VOICE")
    assert ok.success is True
    assert svc.is_confirmation_granted(review.review_token) is True

    # Switching plans invalidates prior confirmation
    other = subscription_provider.get_offer("sub_dev_sandbox_team")
    assert other is not None
    new_review = svc.prepare_review(other)
    assert svc.is_confirmation_granted(review.review_token) is False
    assert svc.is_confirmation_granted(new_review.review_token) is False


def test_subscription_api_create_blocked_without_confirmation_and_succeeds_with_mocked_sandbox():
    # Prepare review via API
    rev_res = client.post("/api/subscriptions/review", json={"offer_id": "sub_dev_api_pro"})
    assert rev_res.status_code == 200
    review_token = rev_res.json()["review_token"]

    # Attempt create before confirmation -> 403
    blocked = client.post("/api/subscriptions/paypal/create", json={"review_token": review_token})
    assert blocked.status_code == 403

    # Casual confirmation rejected
    bad_conf = client.post(
        "/api/subscriptions/confirm",
        json={"review_token": review_token, "spoken_phrase": "Subscribe", "method": "VOICE"},
    )
    assert bad_conf.status_code == 200
    assert bad_conf.json()["success"] is False

    # Exact confirmation accepted
    good_conf = client.post(
        "/api/subscriptions/confirm",
        json={
            "review_token": review_token,
            "spoken_phrase": "Confirm $19.99 monthly subscription",
            "method": "VOICE",
        },
    )
    assert good_conf.status_code == 200
    assert good_conf.json()["success"] is True

    # Mock PayPal Sandbox HTTP responses
    prod_resp = MagicMock(status_code=201)
    prod_resp.json.return_value = {"id": "PROD-TEST123"}

    plan_resp = MagicMock(status_code=201)
    plan_resp.json.return_value = {"id": "P-TEST456"}

    sub_resp = MagicMock(status_code=201)
    sub_resp.json.return_value = {
        "id": "I-TESTSUB789",
        "status": "APPROVAL_PENDING",
        "links": [
            {"rel": "approve", "href": "https://www.sandbox.paypal.com/webapps/billing/subscriptions?ba_token=BA-TEST"}
        ],
    }

    status_resp = MagicMock(status_code=200)
    status_resp.json.return_value = {"id": "I-TESTSUB789", "status": "ACTIVE"}

    cancel_resp = MagicMock(status_code=204)

    async def fake_post(url, *args, **kwargs):
        if url.endswith("/v1/catalogs/products"):
            return prod_resp
        if url.endswith("/v1/billing/plans"):
            return plan_resp
        if url.endswith("/v1/billing/subscriptions"):
            return sub_resp
        if url.endswith("/cancel"):
            return cancel_resp
        raise AssertionError(f"Unexpected POST url: {url}")

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post = AsyncMock(side_effect=fake_post)
    mock_client.get = AsyncMock(return_value=status_resp)

    with patch("app.services.paypal_subscription_service.payment_service.get_access_token", new=AsyncMock(return_value="sandbox-token")), \
         patch("app.services.paypal_subscription_service.paypal_subscription_service.is_sandbox_configured", return_value=True), \
         patch("app.services.paypal_subscription_service.db.get_paypal_catalog_cache", return_value=None), \
         patch("app.services.paypal_subscription_service.db.save_paypal_catalog_cache"), \
         patch("app.services.paypal_subscription_service.httpx.AsyncClient", return_value=mock_client):

        create_res = client.post(
            "/api/subscriptions/paypal/create",
            json={
                "review_token": review_token,
                "return_url": "http://127.0.0.1:5173/?paypal_sub_return=1",
                "cancel_url": "http://127.0.0.1:5173/?paypal_sub_cancel=1",
            },
        )
        assert create_res.status_code == 200
        sub_data = create_res.json()
        assert sub_data["paypal_subscription_id"] == "I-TESTSUB789"
        assert sub_data["status"] == "APPROVAL_PENDING"
        assert "sandbox.paypal.com" in sub_data["approval_url"]

        # Status check updates to ACTIVE
        st_res = client.get("/api/subscriptions/paypal/status/I-TESTSUB789")
        assert st_res.status_code == 200
        assert st_res.json()["status"] == "ACTIVE"

        # Casual cancel rejected
        bad_cancel = client.post(
            "/api/subscriptions/I-TESTSUB789/cancel",
            json={"confirmation_phrase": "Yes"},
        )
        assert bad_cancel.status_code == 400

        # Explicit deterministic cancel accepted
        good_cancel = client.post(
            "/api/subscriptions/I-TESTSUB789/cancel",
            json={"confirmation_phrase": "Confirm cancellation of Developer API Pro — Demo Subscription."},
        )
        assert good_cancel.status_code == 200
        assert good_cancel.json()["status"] == "CANCELLED"
