import pytest
from app.models.purchase import PurchaseState
from app.services.cart_service import cart_service
from app.services.confirmation_service import confirmation_service
from app.services.accessibility_service import accessibility_service
from app.db.seed_data import seed_database


@pytest.fixture(autouse=True)
def setup_test_state():
    seed_database()
    cart_service.clear()
    confirmation_service.reset()
    accessibility_service.reset_to_defaults()


def test_product_selection_never_causes_payment():
    """Invariant 1: Adding or selecting a product must NEVER trigger payment authorization."""
    cart_service.add_item("prod_headphone_sony", quantity=1)
    cart = cart_service.get_cart()
    
    assert cart.item_count == 1
    assert confirmation_service.get_state() == PurchaseState.BROWSING
    assert confirmation_service.get_active_review() is None


def test_payment_review_preparation_does_not_charge():
    """Invariant 2: Preparing review does not authorize payment."""
    cart_service.add_item("prod_headphone_sony", quantity=1)
    review = confirmation_service.prepare_payment_review()
    
    assert review.state == PurchaseState.PAYMENT_REVIEW
    assert review.total_today == 59.36
    assert confirmation_service.get_state() == PurchaseState.PAYMENT_REVIEW


def test_ambiguous_phrase_rejected():
    """Invariant 3: Statements like 'that looks good' or 'yes' must NOT authorize payment."""
    cart_service.add_item("prod_headphone_sony", quantity=1)
    review = confirmation_service.prepare_payment_review()

    # User says "That looks good"
    res1 = confirmation_service.validate_confirmation(
        token=review.review_token,
        spoken_phrase="That looks good",
        confirmation_method="VOICE"
    )
    assert res1.success is False
    assert res1.is_ambiguous is True
    assert "No payment has been made" in res1.message

    # User says "Yes"
    res2 = confirmation_service.validate_confirmation(
        token=review.review_token,
        spoken_phrase="Yes",
        confirmation_method="VOICE"
    )
    assert res2.success is False
    assert res2.is_ambiguous is True
    assert "No payment has been made" in res2.message


def test_exact_phrase_authorization_succeeds():
    """Invariant 4: Exact phrase 'Confirm $59.36 purchase' successfully authorizes payment."""
    cart_service.add_item("prod_headphone_sony", quantity=1)
    review = confirmation_service.prepare_payment_review()

    res = confirmation_service.validate_confirmation(
        token=review.review_token,
        spoken_phrase="Confirm $59.36 purchase",
        confirmation_method="VOICE"
    )
    assert res.success is True
    assert res.state == PurchaseState.PAYMENT_PROCESSING
    assert res.amount_charged == 59.36


def test_high_value_purchase_requires_two_steps():
    """Invariant 5: Purchases above $500 require a 2-step confirmation gate."""
    cart_service.add_item("prod_laptop_dell", quantity=1)
    review = confirmation_service.prepare_payment_review()

    assert review.is_high_value is True
    assert review.high_value_total_steps == 2
    assert review.high_value_step == 1

    # Attempt 1: advances to Step 2
    res_step1 = confirmation_service.validate_confirmation(
        token=review.review_token,
        spoken_phrase=review.expected_phrase,
        confirmation_method="VOICE",
        high_value_step=1
    )
    assert res_step1.success is False
    assert res_step1.requires_step == 2
    assert "Step 1 verified" in res_step1.message

    # Attempt 2: final authorization succeeds
    res_step2 = confirmation_service.validate_confirmation(
        token=review.review_token,
        spoken_phrase=review.expected_phrase,
        confirmation_method="VOICE",
        high_value_step=2
    )
    assert res_step2.success is True
    assert res_step2.state == PurchaseState.PAYMENT_PROCESSING


def test_price_change_invalidates_confirmation():
    """Invariant 6: If price changes between review and confirm, authorization is revoked."""
    cart_service.add_item("prod_keyboard_logitech", quantity=1)
    review = confirmation_service.prepare_payment_review()
    
    # Simulate merchant raising price
    confirmation_service.simulate_price_change(62.99)

    res = confirmation_service.validate_confirmation(
        token=review.review_token,
        spoken_phrase=review.expected_phrase,
        confirmation_method="VOICE"
    )
    assert res.success is False
    assert "The price changed" in res.message


def test_cancellation_anytime():
    """Invariant 7: User can cancel anytime and no charge occurs."""
    cart_service.add_item("prod_headphone_sony", quantity=1)
    confirmation_service.prepare_payment_review()

    res = confirmation_service.cancel_purchase("User commanded cancellation")
    assert res.success is True
    assert res.state == PurchaseState.CANCELLED
    assert "No payment was made" in res.message


def test_subscription_requires_acknowledgement():
    """Invariant 8: Recurring subscriptions require explicit recurring acknowledgement."""
    cart_service.add_item("prod_subscription_music", quantity=1)
    review = confirmation_service.prepare_payment_review()

    assert review.is_subscription is True

    # Without subscription_ack
    res = confirmation_service.validate_confirmation(
        token=review.review_token,
        spoken_phrase=review.expected_phrase,
        confirmation_method="VOICE",
        subscription_ack=False
    )
    assert res.success is False
    assert "Explicit acknowledgement of recurring terms is required" in res.message
