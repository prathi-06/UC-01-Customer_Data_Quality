import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL or not DATABASE_URL.strip():
    raise RuntimeError(
        "DATABASE_URL environment variable is not set. Please set DATABASE_URL in .env "
        "(e.g., postgresql+psycopg://user:password@host/dbname?sslmode=require or local postgresql+psycopg://user:pass@localhost:5432/dbname)"
    )

PLACEHOLDER_JWT_SECRET = "CHANGE_ME_generate_with_secrets_token_urlsafe_48"
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET or len(JWT_SECRET.strip()) < 32 or JWT_SECRET.strip() == PLACEHOLDER_JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET is missing, shorter than 32 characters, or using the default placeholder.\n"
        "Please generate a secure JWT secret using Python:\n"
        "    python -c \"import secrets; print(secrets.token_urlsafe(48))\"\n"
        "and set JWT_SECRET in your .env file."
    )

SUBSCRIPTION_STORE = os.getenv("SUBSCRIPTION_STORE", "file")
ENABLE_TEST_HOOKS = os.getenv("ENABLE_TEST_HOOKS", "false").lower() in ("true", "1", "yes")
