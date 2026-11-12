from fastapi import APIRouter
from typing import Dict, Any, List
from app.db.seed_data import seed_database
from app.services.cart_service import cart_service
from app.services.confirmation_service import confirmation_service
from app.services.accessibility_service import accessibility_service
from app.services.payment_service import payment_service
from app.services.ai_service import ai_service
from app.services.product_service import product_service

router = APIRouter(prefix="/demo", tags=["System"])

DEMO_SCENARIOS = [
    {
        "id": 1,
        "title": "Scenario 1: Agentic Search, Compare & Cheaper Alternative",
        "description": "User searches 'wireless headphones under $80', asks AI to compare top 2, then requests cheaper alternative.",
        "initial_command": "Find wireless headphones under $80",
        "recommended_next_commands": [
            "Compare the first two",
            "Show me something cheaper"
        ]
    },
    {
        "id": 2,
        "title": "Scenario 2: Ambiguity Protection ('That looks good')",
        "description": "User says 'That one looks good.' System selects product but explicitly warns: NO PAYMENT HAS BEEN MADE.",
        "initial_command": "That one looks good",
        "expected_behavior": "Product selected; confirmation gate remains locked. 'No payment has been made.'"
    },
    {
        "id": 3,
        "title": "Scenario 3: Exact-Amount Confirmation Protection ($59.36)",
        "description": "System requires 'Confirm $59.36 purchase'. Casual 'Yes' is rejected; only exact phrase authorizes payment.",
        "initial_command": "Prepare checkout",
        "test_reject_command": "Yes",
        "test_accept_command": "Confirm $59.36 purchase"
    },
    {
        "id": 4,
        "title": "Scenario 4: Subscription Guardian ($9.99/mo)",
        "description": "Clearly detects and explains recurring charges. Requires explicit recurring-payment acknowledgement.",
        "initial_command": "Search Audible Access Subscription",
        "cart_product_id": "prod_subscription_music"
    },
    {
        "id": 5,
        "title": "Scenario 5: High-Value Purchase Two-Step Confirmation ($799)",
        "description": "Dell XPS Laptop ($799) exceeds $500 threshold, mandating 2-step verification before payment execution.",
        "initial_command": "Search Dell XPS 13 Laptop",
        "cart_product_id": "prod_laptop_dell"
    },
    {
        "id": 6,
        "title": "Scenario 6: Large Controls Mode",
        "description": "Instantly activates oversized high-contrast interaction targets with generous spacing.",
        "target_mode": "LARGE_CONTROLS"
    },
    {
        "id": 7,
        "title": "Scenario 7: Full Keyboard-Only Navigation",
        "description": "Navigates entire flow via Tab, Shift+Tab, Enter, Space, and Escape with high-contrast visible focus rings.",
        "target_mode": "KEYBOARD"
    },
    {
        "id": 8,
        "title": "Scenario 8: Switch-Compatible Mode (Browser Demonstration)",
        "description": "Cycles highlight between CONFIRM -> CANCEL -> BACK. Space bar triggers switch input.",
        "target_mode": "SWITCH"
    },
    {
        "id": 9,
        "title": "Scenario 9: Price-Change Invalidation ($54.99 -> $62.99)",
        "description": "Simulates price change right before payment authorization. Immediately invalidates previous confirmation.",
        "old_price": 54.99,
        "new_price": 62.99
    },
    {
        "id": 10,
        "title": "Scenario 10: Graceful PayPal Gateway Failure",
        "description": "Simulates payment decline. Informs user accessibly: 'Nothing was charged. Would you like to try again?'",
        "simulate_failure": True
    },
    {
        "id": 11,
        "title": "Scenario 11: AI + AG Grid Natural Language Filtering",
        "description": "Translates conversational command 'Only show purchases over $50' into real-time AG Grid filters.",
        "grid_command": "Only show purchases over $50"
    },
    {
        "id": 12,
        "title": "Scenario 12: AI + Bryntum Accessible Commerce Timeline",
        "description": "Asks 'What payments are coming next week?' and visually highlights upcoming charges and deliveries.",
        "timeline_command": "What payments are coming next week?"
    },
    {
        "id": 13,
        "title": "Scenario 13: APIMatic & AccessPay Developer Infrastructure",
        "description": "Demonstrates how third-party merchants integrate AccessPay's accessible confirmation SDK.",
        "page": "/developer"
    }
]


@router.get("/scenarios", summary="List demo scenarios", description="Return the built-in AccessPay demonstration scenarios.")
def list_scenarios():
    return {"scenarios": DEMO_SCENARIOS}


@router.post("/reset")
def reset_demo():
    """
    RESET DEMO: Resets shopping session, cart, current product selection,
    and confirmation state without altering secrets or environment configuration.
    """
    seed_database()
    cart_service.clear()
    confirmation_service.reset()
    accessibility_service.reset_to_defaults()
    ai_service.reset_conversation()
    product_service.reset_session()
    payment_service.reset_idempotency_state()
    
    return {
        "status": "success",
        "message": "Demo state reset successfully. Shopping session, cart, selection, and confirmation state cleared."
    }


@router.post("/scenario/{scenario_id}")
async def load_scenario(scenario_id: int):
    """Deterministically sets up state for a specific demo scenario."""
    if scenario_id == 1:
        # Scenario 1: Pre-load headphones in search
        cart_service.clear()
        confirmation_service.reset()
        res = await ai_service.process_user_intent("Find wireless headphones under $80")
        return {"scenario": 1, "result": res}

    elif scenario_id == 2:
        # Scenario 2: Search headphones, prepare for "That one looks good"
        cart_service.clear()
        confirmation_service.reset()
        await ai_service.process_user_intent("Find wireless headphones under $80")
        res = await ai_service.process_user_intent("That one looks good")
        return {"scenario": 2, "result": res}

    elif scenario_id == 3:
        # Scenario 3: Headphone in cart with total $59.36 and review prepared
        cart_service.clear()
        cart_service.add_item("prod_headphone_sony", quantity=1)
        review = confirmation_service.prepare_payment_review()
        return {
            "scenario": 3,
            "message": "Cart loaded with Sony Headphones ($59.36). Say 'Confirm $59.36 purchase' or try ambiguous 'Yes'.",
            "review": review.model_dump()
        }

    elif scenario_id == 4:
        # Scenario 4: Subscription in cart
        cart_service.clear()
        cart_service.add_item("prod_subscription_music", quantity=1)
        review = confirmation_service.prepare_payment_review()
        return {
            "scenario": 4,
            "message": "Subscription loaded: $9.99/month. Explicit recurring-payment acknowledgement required.",
            "review": review.model_dump()
        }

    elif scenario_id == 5:
        # Scenario 5: High-value laptop in cart ($799)
        cart_service.clear()
        cart_service.add_item("prod_laptop_dell", quantity=1)
        review = confirmation_service.prepare_payment_review()
        return {
            "scenario": 5,
            "message": "Laptop ($799.00) loaded. 2-Step confirmation initiated because amount exceeds $500 threshold.",
            "review": review.model_dump()
        }

    elif scenario_id == 6:
        # Large controls mode
        accessibility_service.set_mode("LARGE_CONTROLS")
        return {"scenario": 6, "mode": "LARGE_CONTROLS"}

    elif scenario_id == 7:
        # Keyboard mode
        accessibility_service.set_mode("KEYBOARD")
        return {"scenario": 7, "mode": "KEYBOARD"}

    elif scenario_id == 8:
        # Switch mode
        accessibility_service.set_mode("SWITCH")
        return {"scenario": 8, "mode": "SWITCH"}

    elif scenario_id == 9:
        # Price change simulation
        cart_service.clear()
        cart_service.add_item("prod_keyboard_logitech", quantity=1)
        confirmation_service.prepare_payment_review()
        updated_review = confirmation_service.simulate_price_change(62.99)
        return {
            "scenario": 9,
            "message": "Price change triggered from $54.99 to $62.99. Prior review invalidated.",
            "review": updated_review.model_dump()
        }

    elif scenario_id == 10:
        # Simulate payment failure
        payment_service.set_simulate_failure(True)
        cart_service.clear()
        cart_service.add_item("prod_headphone_sony", quantity=1)
        confirmation_service.prepare_payment_review()
        return {
            "scenario": 10,
            "message": "Payment failure simulation enabled. Next payment attempt will gracefully decline without charging."
        }

    return {"scenario": scenario_id, "status": "loaded"}
