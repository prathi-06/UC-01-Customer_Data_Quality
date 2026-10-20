import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/customer_saas?sslmode=require")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-key-change-in-prod")
SUBSCRIPTION_STORE = os.getenv("SUBSCRIPTION_STORE", "file")
ENABLE_TEST_HOOKS = os.getenv("ENABLE_TEST_HOOKS", "false").lower() in ("true", "1", "yes")
