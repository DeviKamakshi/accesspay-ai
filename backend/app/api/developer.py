from fastapi import APIRouter
from app.config import settings

router = APIRouter(prefix="/developer", tags=["Developer"])

DEVELOPER_SPECS = {
    "title": "AccessPay for Merchants",
    "subtitle": "Add voice-first shopping and safer payment confirmation to existing commerce experiences.",
    "status": "Prototype Merchant API",
    "production_note": (
        "Production deployment would add merchant authentication, tenant isolation, "
        "rate limiting, API versioning, webhooks, and audit controls."
    ),
    "runtime_architecture": {
        "flow": "User / Merchant App -> AccessPay API -> (Google Gemini Intent + Channel3 Products + PayPal Sandbox Payments)",
        "note": "User payment traffic runs strictly through PayPal Sandbox. APIMatic is NOT in the runtime payment path.",
    },
    "development_architecture": {
        "flow": "Developer / AI Coding Agent -> APIMatic Context Plugin (paypal) -> Authoritative PayPal API/SDK Context -> AccessPay PayPal Integration",
        "install_command": "npx context-plugins install paypal",
        "workspace_skills_path": ".agents/skills/python-*",
        "credential_required": False,
        "contributions": [
            "Authoritative PayPal API and SDK context during development",
            "OAuth 2.0 client credentials and Sandbox base URL verification",
            "Orders API v2 create/get/capture request and error-union validation",
            "Subscriptions API v1 billing plan, subscription create/get/cancel verification",
            "Reducing reliance on manually remembered or outdated PayPal API details",
        ],
    },
    "apimatic_verification_report": [
        {"area": "PayPal OAuth / Authentication", "verified": "YES", "notes": "OAuth 2.0 client_credentials against https://api-m.sandbox.paypal.com/v1/oauth2/token with token caching."},
        {"area": "Orders Create (POST /v2/checkout/orders)", "verified": "YES", "notes": "intent=CAPTURE, purchase_units amount/currency_code, PayPal-Request-Id, application_context."},
        {"area": "Approval URL Handling", "verified": "YES", "notes": "Extracts HATEOAS links[rel='approve'] for Sandbox buyer approval."},
        {"area": "Orders Capture (POST /v2/checkout/orders/{id}/capture)", "verified": "YES", "notes": "Verifies APPROVED state before capture and records real capture ID."},
        {"area": "Return / Cancel URLs", "verified": "YES", "notes": "Canonical return_url/cancel_url handling with server-side status verification on redirect."},
        {"area": "Subscriptions Plans & Lifecycle (v1/billing/*)", "verified": "YES", "notes": "Covered by paypal SDK subscriptions controller (create_billing_plan, create_subscription, get_subscription, cancel_subscription)."},
        {"area": "Catalog Products (POST /v1/catalogs/products)", "verified": "NOT COVERED", "notes": "Not included in the 5 controllers of APIMatic paypal v2.29; verified against PayPal REST docs."},
        {"area": "Error Handling", "verified": "YES", "notes": "Matches Error / SubscriptionError (name, message, debug_id) guidance; never exposes secrets or raw payloads to UI."},
    ],
    "endpoint_groups": {
        "SHOPPING / AI": [
            {"method": "POST", "path": "/api/ai/intent", "purpose": "Natural-language product discovery and conversational follow-ups"},
            {"method": "POST", "path": "/api/products/search", "purpose": "Search verified physical products via Channel3"},
            {"method": "POST", "path": "/api/products/compare", "purpose": "Compare selected products"},
        ],
        "SAVED": [
            {"method": "GET", "path": "/api/saved/items", "purpose": "List saved items"},
            {"method": "GET", "path": "/api/saved/searches", "purpose": "List saved searches"},
            {"method": "GET", "path": "/api/saved/history", "purpose": "List recent search history"},
        ],
        "CART": [
            {"method": "GET", "path": "/api/cart", "purpose": "Fetch current shopping cart"},
            {"method": "POST", "path": "/api/cart/items", "purpose": "Add verified physical product to cart"},
        ],
        "CHECKOUT / PURCHASE": [
            {"method": "POST", "path": "/api/purchase/review", "purpose": "Compute server-authoritative totals and review token"},
            {"method": "POST", "path": "/api/purchase/confirm", "purpose": "Verify explicit exact-amount confirmation"},
        ],
        "ORDERS": [
            {"method": "GET", "path": "/api/orders", "purpose": "List completed one-time orders"},
            {"method": "GET", "path": "/api/orders/{order_id}", "purpose": "Fetch single order details"},
        ],
        "PAYMENTS": [
            {"method": "POST", "path": "/api/payments/paypal/create-order", "purpose": "Create PayPal Sandbox order after explicit confirmation"},
            {"method": "POST", "path": "/api/payments/paypal/capture-order/{order_id}", "purpose": "Capture approved PayPal Sandbox order"},
        ],
        "SUBSCRIPTIONS": [
            {"method": "GET", "path": "/api/subscriptions/products", "purpose": "List isolated Demo Subscription Catalog plans"},
            {"method": "POST", "path": "/api/subscriptions/review", "purpose": "Prepare recurring subscription review"},
            {"method": "POST", "path": "/api/subscriptions/confirm", "purpose": "Verify exact recurring amount + billing frequency"},
            {"method": "POST", "path": "/api/subscriptions/paypal/create", "purpose": "Create PayPal Sandbox subscription after confirmation"},
            {"method": "GET", "path": "/api/subscriptions/paypal/status/{subscription_id}", "purpose": "Check PayPal Sandbox subscription status"},
            {"method": "POST", "path": "/api/subscriptions/{subscription_id}/cancel", "purpose": "Cancel subscription after explicit cancellation phrase"},
        ],
    },
}


@router.get("/overview", summary="Get developer architecture overview", description="Return AccessPay Merchant API endpoints, integration guides, and non-secret provider readiness status.")
def get_developer_overview():
    return {
        **DEVELOPER_SPECS,
        "environment_status": {
            "paypal_sandbox": "Configured ✓" if (settings.PAYPAL_CLIENT_ID and settings.PAYPAL_CLIENT_SECRET) else "Not Configured",
            "channel3_products": "Configured ✓" if settings.CHANNEL3_API_KEY else "Not Configured",
            "google_gemini_ai": "Configured ✓" if settings.GEMINI_API_KEY else "Not Configured",
            "apimatic_context_plugin": "Configured ✓ (Development Context)",
        },
    }
