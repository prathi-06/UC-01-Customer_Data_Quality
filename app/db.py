from sqlalchemy import create_engine
from app.config import DATABASE_URL

# Sync engine with a small connection pool, SQLAlchemy 2.0 Core
def get_db_url() -> str:
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://") and not url.startswith("postgresql+psycopg://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

engine = create_engine(
    get_db_url(),
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=300,
)
