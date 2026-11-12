import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api import (
    products,
    cart,
    purchase,
    payments,
    orders,
    saved,
    accessibility,
    ai,
    timeline,
    analytics,
    demo,
    developer,
    subscriptions
)
from app.services.payment_service import payment_service
from app.services.product_service import product_service
from app.services.ai_service import ai_service
from app.db.database import db
from app.db.seed_data import ensure_database_seeded

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("accesspay.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_database_seeded()

    # Diagnostic check on configured providers (never logs credential values)
    if settings.AI_PROVIDER.lower() == "gemini" and not settings.GEMINI_API_KEY.strip():
        logger.warning("AI_PROVIDER=gemini but Gemini API key missing in backend/.env.")
    elif settings.AI_PROVIDER.lower() == "openai" and not settings.OPENAI_API_KEY.strip():
        logger.warning("AI_PROVIDER=openai but OpenAI API key missing in backend/.env.")

    if settings.PRODUCT_PROVIDER.lower() == "channel3" and not settings.CHANNEL3_API_KEY.strip():
        logger.warning("PRODUCT_PROVIDER=channel3 but Channel3 API key missing in backend/.env.")

    if settings.PAYMENT_PROVIDER.lower() == "paypal":
        if not settings.PAYPAL_CLIENT_ID.strip():
            logger.warning("PAYMENT_PROVIDER=paypal but PayPal Client ID missing in backend/.env.")
        if not settings.PAYPAL_CLIENT_SECRET.strip():
            logger.warning("PAYMENT_PROVIDER=paypal but PayPal Secret missing in backend/.env.")

    logger.info(
        "AccessPay AI starting up (version=%s, env_file=%s, paypal_env=sandbox, ai_provider=%s, product_provider=%s, payment_provider=%s)",
        settings.VERSION,
        settings.ENV_FILE_LOADED,
        ai_service.llm_service.get_provider_name(),
        product_service.get_active_provider_mode(),
        payment_service.get_active_provider(),
    )
    yield
    logger.info("AccessPay AI shutting down.")


OPENAPI_TAGS = [
    {"name": "AI & Intent", "description": "Natural-language shopping intent orchestration powered by Google Gemini (NLU only; does not supply authoritative prices, cart totals, or payment authorization)."},
    {"name": "Products", "description": "Product discovery, comparison, and session search. Channel3 is the configured real-commerce provider in this hackathon prototype; future deployments may plug in merchant catalogs."},
    {"name": "Saved", "description": "Saved items, saved searches, and recent search history."},
    {"name": "Cart", "description": "Shopping cart management and server-computed item totals."},
    {"name": "Checkout", "description": "Purchase review and deterministic exact-amount human confirmation gates. AI may never silently authorize payment."},
    {"name": "Orders", "description": "Completed one-time order history, tracking, and reorder preparation."},
    {"name": "Payments", "description": "PayPal Sandbox Orders API v2 creation, buyer approval verification, and capture."},
    {"name": "Subscriptions", "description": "Isolated Demo Subscription Catalog and PayPal Sandbox Subscriptions API v1 workflows requiring exact recurring amount + billing frequency confirmation."},
    {"name": "Developer", "description": "Prototype Merchant API overview and APIMatic context verification metadata."},
    {"name": "System", "description": "Health probes, accessibility settings, activity timeline, analytics, and demo utilities."},
]

app = FastAPI(
    title="AccessPay Merchant API",
    description=(
        "Voice-first accessible commerce APIs for conversational product discovery, "
        "shopping-session management, cart operations, safer checkout, order history, "
        "and PayPal-powered payment workflows.\n\n"
        "**Prototype Notice:** Prototype API. Production merchant authentication and tenant isolation are not yet implemented.\n\n"
        "**Safety Boundary:** AI (Google Gemini) interprets natural-language intent and conversational follow-ups, "
        "while product prices, cart totals, confirmation gates, and PayPal Sandbox execution remain strictly server-authoritative."
    ),
    version=settings.VERSION,
    contact={"name": "AccessPay AI Team"},
    servers=[
        {"url": "http://127.0.0.1:8008", "description": "Local Development"},
    ],
    openapi_tags=OPENAPI_TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Explicit CORS configuration for local development and deployed Render frontend (no '*' wildcard)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled backend exception on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=503,
        content={
            "error": True,
            "action": "SEARCH_ERROR",
            "detail": "AccessPay is temporarily unavailable.\nPlease try again.",
            "message": "AccessPay is temporarily unavailable.\nPlease try again.",
        },
    )


# Include all API Routers under /api prefix
app.include_router(products.router, prefix=settings.API_PREFIX)
app.include_router(cart.router, prefix=settings.API_PREFIX)
app.include_router(purchase.router, prefix=settings.API_PREFIX)
app.include_router(payments.router, prefix=settings.API_PREFIX)
app.include_router(orders.router, prefix=settings.API_PREFIX)
app.include_router(saved.router, prefix=settings.API_PREFIX)
app.include_router(accessibility.router, prefix=settings.API_PREFIX)
app.include_router(ai.router, prefix=settings.API_PREFIX)
app.include_router(timeline.router, prefix=settings.API_PREFIX)
app.include_router(analytics.router, prefix=settings.API_PREFIX)
app.include_router(demo.router, prefix=settings.API_PREFIX)
app.include_router(developer.router, prefix=settings.API_PREFIX)
app.include_router(subscriptions.router, prefix=settings.API_PREFIX)


def _build_health_payload():
    db_healthy = True
    try:
        db.get_recent_audit_events(limit=1)
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
        db_healthy = False

    ai_active = ai_service.llm_service.is_configured()
    product_active = (
        product_service.get_active_provider_mode() == "channel3"
        and product_service.channel3_service.is_configured()
    )
    paypal_active = (
        payment_service.get_active_provider() == "paypal"
        and payment_service.is_paypal_configured()
    )

    return {
        "status": "ok" if db_healthy else "degraded",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "env_file": settings.ENV_FILE_LOADED,
        "paypal_environment": "sandbox",
        "providers": {
            "ai": ai_service.llm_service.get_provider_name(),
            "product": product_service.get_active_provider_mode(),
            "payment": payment_service.get_active_provider(),
        },
        "components": {
            "application": "ok",
            "database": "connected" if db_healthy else "unreachable",
            "ai_service": (
                f"ready ({ai_service.llm_service.get_provider_name()} active)"
                if ai_active
                else "ready (deterministic fallback)"
            ),
            "product_service": (
                "ready (Channel3 real product search active)"
                if product_active
                else "ready (curated fallback catalog)"
            ),
            "payment_service": (
                "ready (PayPal Sandbox Orders API active)"
                if paypal_active
                else "ready (PayPal Sandbox demo fallback)"
            ),
        },
    }


@app.get("/health", tags=["System"], summary="Health check")
def health_check():
    """
    Render Health Check endpoint (/health).
    Returns {"status": "ok"} and safe component readiness without exposing any secrets.
    """
    return _build_health_payload()


@app.get("/api/health", tags=["System"], summary="API health check")
def api_health_check():
    """Alias under /api/health for frontend health probes."""
    return _build_health_payload()


# Optional SPA static file mount when deployed as a unified service or container
frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if frontend_dist.is_dir() and (frontend_dist / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="static-assets")


@app.get("/", tags=["System"], summary="Service metadata", description="Return basic service metadata, version, and documentation entrypoints.")
def root():
    return {
        "name": settings.PROJECT_NAME,
        "tagline": settings.TAGLINE,
        "version": settings.VERSION,
        "docs": "/docs",
        "health": "/health",
        "status": "ok"
    }


def _clean_schema_node(node, is_top_level: bool = False):
    if isinstance(node, list):
        for item in node:
            _clean_schema_node(item, is_top_level=False)
        return
    if not isinstance(node, dict):
        return

    if not is_top_level and "title" in node:
        node.pop("title", None)

    if "$ref" in node and len(node) > 1:
        ref_val = node.pop("$ref")
        all_of = node.get("allOf")
        if isinstance(all_of, list):
            all_of.insert(0, {"$ref": ref_val})
        else:
            node["allOf"] = [{"$ref": ref_val}]

    for key, val in list(node.items()):
        if key in ("properties", "$defs", "definitions") and isinstance(val, dict):
            for prop_schema in val.values():
                _clean_schema_node(prop_schema, is_top_level=False)
        elif isinstance(val, (dict, list)):
            _clean_schema_node(val, is_top_level=False)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
        servers=app.servers,
        contact=app.contact,
    )

    schemas = schema.get("components", {}).get("schemas", {})
    seen_titles = set()
    for name, model_schema in schemas.items():
        if isinstance(model_schema, dict):
            title = model_schema.get("title") or name
            if len(title) > 50:
                title = title[:50].rstrip()
            if title in seen_titles:
                title = name[:50]
            seen_titles.add(title)
            model_schema["title"] = title
            _clean_schema_node(model_schema, is_top_level=True)

    used_op_ids = set()
    http_methods = {"get", "post", "put", "delete", "patch", "options", "head", "trace"}
    for path, path_item in schema.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in http_methods or not isinstance(operation, dict):
                continue
            if not (operation.get("description") or "").strip():
                operation["description"] = operation.get("summary") or f"{method.upper()} {path}"

            op_id = operation.get("operationId") or f"{method}_{path}"
            if len(op_id) > 50:
                op_id = op_id[:50].rstrip("_")
            base_id = op_id
            suffix = 2
            while op_id in used_op_ids:
                sfx = f"_{suffix}"
                op_id = f"{base_id[:50 - len(sfx)]}{sfx}"
                suffix += 1
            used_op_ids.add(op_id)
            operation["operationId"] = op_id

            for param in operation.get("parameters", []) or []:
                if isinstance(param, dict) and isinstance(param.get("schema"), dict):
                    _clean_schema_node(param["schema"], is_top_level=False)

            req_body = operation.get("requestBody")
            if isinstance(req_body, dict):
                for media in (req_body.get("content") or {}).values():
                    if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                        _clean_schema_node(media["schema"], is_top_level=False)

            for resp in (operation.get("responses") or {}).values():
                if isinstance(resp, dict):
                    for media in (resp.get("content") or {}).values():
                        if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                            _clean_schema_node(media["schema"], is_top_level=False)

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
