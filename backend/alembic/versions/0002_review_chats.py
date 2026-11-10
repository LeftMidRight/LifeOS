"""review chat sessions and messages

Revision ID: 0002_review_chats
Revises: 0001_initial
Create Date: 2026-11-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0002_review_chats"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_chat_sessions",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("scope", sa.String(10), nullable=False),
        sa.Column("period_start", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("period_end", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.Column("latest_sequence", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "period_start", name="uq_review_chat_period"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.execute(
        "CREATE INDEX idx_review_chat_sessions_recent "
        "ON review_chat_sessions (updated_at DESC, id DESC)"
    )

    op.create_table(
        "review_chat_messages",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("session_id", sa.CHAR(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", mysql.MEDIUMTEXT(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=3), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "sequence", name="uq_review_chat_message_seq"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["review_chat_sessions.id"],
            name="fk_review_chat_messages_session",
            ondelete="CASCADE",
        ),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )


def downgrade() -> None:
    op.drop_table("review_chat_messages")
    op.drop_index("idx_review_chat_sessions_recent", table_name="review_chat_sessions")
    op.drop_table("review_chat_sessions")
