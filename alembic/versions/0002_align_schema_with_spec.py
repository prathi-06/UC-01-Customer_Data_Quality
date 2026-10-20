"""0002 align schema with spec digest

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20

"""
from typing import Sequence, Union
from alembic import op

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("""
    ALTER TABLE runs ADD COLUMN IF NOT EXISTS request_json JSONB;
    ALTER TABLE runs ADD COLUMN IF NOT EXISTS result_json JSONB;
    ALTER TABLE runs ADD COLUMN IF NOT EXISTS error_message TEXT;
    ALTER TABLE runs ADD COLUMN IF NOT EXISTS submitted_by VARCHAR(64);
    ALTER TABLE runs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
    """)

    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'check_accepted_runs_non_negative'
        ) THEN
            ALTER TABLE daily_usage ADD CONSTRAINT check_accepted_runs_non_negative CHECK (accepted_runs >= 0);
        END IF;
    END $$;
    """)

def downgrade() -> None:
    op.execute("ALTER TABLE daily_usage DROP CONSTRAINT IF EXISTS check_accepted_runs_non_negative;")
    op.execute("""
    ALTER TABLE runs DROP COLUMN IF EXISTS completed_at;
    ALTER TABLE runs DROP COLUMN IF EXISTS submitted_by;
    ALTER TABLE runs DROP COLUMN IF EXISTS error_message;
    ALTER TABLE runs DROP COLUMN IF EXISTS result_json;
    ALTER TABLE runs DROP COLUMN IF EXISTS request_json;
    """)
