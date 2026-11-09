"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entries",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("content", mysql.MEDIUMTEXT(), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("occurred_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("amount", sa.DECIMAL(12, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="CNY"),
        sa.Column("category", sa.String(20), nullable=True),
        sa.Column("status", sa.String(10), nullable=True),
        sa.Column("due_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.Column("mood", sa.Integer(), nullable=True),
        sa.Column("energy", sa.Integer(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("(JSON_ARRAY())")),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("(JSON_OBJECT())")),
        sa.Column("source", sa.String(16), nullable=False, server_default="manual"),
        sa.Column("deleted_at", mysql.DATETIME(fsp=3), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.execute("CREATE INDEX idx_entries_occurred ON entries (occurred_at DESC)")
    op.execute("CREATE INDEX idx_entries_kind ON entries (kind, occurred_at DESC)")
    op.create_index("idx_entries_status", "entries", ["status", "due_at"])

    op.create_table(
        "ai_insights",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("scope", sa.String(10), nullable=False),
        sa.Column("period_start", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("period_end", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.execute("CREATE INDEX idx_insights_period ON ai_insights (scope, period_start DESC)")


def downgrade() -> None:
    op.drop_table("ai_insights")
    op.drop_table("entries")
