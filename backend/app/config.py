import os
from pathlib import Path
from typing import List
from pydantic import BaseModel
from dotenv import load_dotenv

# Load .env strictly from backend/.env (with optional root .env fallback only if backend/.env is absent)
backend_env_path = Path(__file__).resolve().parent.parent / ".env"
root_env_path = Path(__file__).resolve().parent.parent.parent / ".env"

if backend_env_path.is_file():
    load_dotenv(dotenv_path=backend_env_path, override=True)
    _ENV_FILE_LOADED = "backend/.env"
elif root_env_path.is_file():
    load_dotenv(dotenv_path=root_env_path, override=True)
    _ENV_FILE_LOADED = ".env"
else:
    _ENV_FILE_LOADED = "environment variables only (no .env file found)"


def _build_cors_origins() -> List[str]:
    origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8008",
        "http://127.0.0.1:8008",
        "https://accesspay-frontend.onrender.com",
        "https://accesspay-ai.onrender.com",
        "https://accesspay-api.onrender.com",
    ]
    frontend_origin = os.getenv("FRONTEND_ORIGIN", "").strip()
    if frontend_origin:
        for origin in frontend_origin.split(","):
            cleaned = origin.strip().rstrip("/")
            if cleaned and cleaned not in origins:
                origins.append(cleaned)
    return origins


class Settings(BaseModel):
    PROJECT_NAME: str = "AccessPay AI"
    TAGLINE: str = "AI does the navigating. You make the decisions."
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8008"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # SQLite persistence (supports Render Persistent Disk or local file)
    DATABASE_PATH: str = os.getenv(
        "DATABASE_PATH",
        str(Path(__file__).resolve().parent.parent / "accesspay.db")
    )

    # AI Configuration (Gemini / OpenAI / Deterministic Agentic Fallback)
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "auto")  # 'gemini', 'openai', 'mock', 'auto'
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Product Search Provider ('channel3', 'mock', or 'auto')
    PRODUCT_PROVIDER: str = os.getenv("PRODUCT_PROVIDER", "auto")
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "false").lower() == "true"
    ENV_FILE_LOADED: str = _ENV_FILE_LOADED

    # Channel3 E-commerce Integration (Backend-only credentials)
    CHANNEL3_API_KEY: str = os.getenv("CHANNEL3_API_KEY", "")
    CHANNEL3_BASE_URL: str = os.getenv("CHANNEL3_BASE_URL", "https://api.trychannel3.com/v1")

    # PayPal Sandbox Integration (Strictly Sandbox Only, NEVER Live)
    PAYMENT_PROVIDER: str = os.getenv("PAYMENT_PROVIDER", "auto")  # 'paypal', 'mock', or 'auto'
    PAYPAL_ENVIRONMENT: str = "sandbox"  # Hard-enforced to sandbox; never allow live money
    PAYPAL_MODE: str = "sandbox"
    PAYPAL_CLIENT_ID: str = os.getenv("PAYPAL_CLIENT_ID", "")
    PAYPAL_CLIENT_SECRET: str = os.getenv("PAYPAL_CLIENT_SECRET", "")
    PAYPAL_BASE_URL: str = "https://api-m.sandbox.paypal.com"

    # Optional Frontend Origin for Render CORS
    FRONTEND_ORIGIN: str = os.getenv("FRONTEND_ORIGIN", "")

    # Explicit CORS settings (no wildcard '*' in production)
    CORS_ORIGINS: List[str] = _build_cors_origins()
    CORS_ORIGIN_REGEX: str = r"^https://[a-zA-Z0-9-]+\.onrender\.com$"


settings = Settings()
