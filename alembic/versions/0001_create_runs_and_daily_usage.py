"""0001 create runs and daily_usage

Revision ID: 0001
Revises: 
Create Date: 2026-10-20

"""
from typing import Sequence, Union
from alembic import op

revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS runs (
        run_id VARCHAR(36) PRIMARY KEY,
        tenant_id VARCHAR(64) NOT NULL,
        idempotency_key VARCHAR(128) NOT NULL,
        input_fingerprint VARCHAR(64) NOT NULL,
        operation VARCHAR(32) NOT NULL,
        status VARCHAR(32) NOT NULL,
        result JSONB,
        error JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        finished_at TIMESTAMPTZ,
        CONSTRAINT uq_tenant_idempotency_key UNIQUE (tenant_id, idempotency_key)
    );
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS daily_usage (
        tenant_id VARCHAR(64) NOT NULL,
        usage_date_utc DATE NOT NULL,
        accepted_runs INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (tenant_id, usage_date_utc)
    );
    """)

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS daily_usage;")
    op.execute("DROP TABLE IF EXISTS runs;")
