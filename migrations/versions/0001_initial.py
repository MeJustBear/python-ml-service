"""Журнал инференсов и события моделей

Revision ID: 0001
Revises:
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "inference_log",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("batch_size", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("principal", sa.String(length=128), nullable=True),
        sa.Column("payload", JSONType, nullable=True),
        sa.Column("result", JSONType, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_inference_log_model_name", "inference_log", ["model_name"])
    op.create_index("ix_inference_log_status", "inference_log", ["status"])
    op.create_index("ix_inference_log_created_at", "inference_log", ["created_at"])
    op.create_index("ix_inference_log_model_created", "inference_log", ["model_name", "created_at"])

    op.create_table(
        "model_event",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("event", sa.String(length=32), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("details", JSONType, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_model_event_model_name", "model_event", ["model_name"])
    op.create_index("ix_model_event_event", "model_event", ["event"])
    op.create_index("ix_model_event_created_at", "model_event", ["created_at"])


def downgrade() -> None:
    op.drop_table("model_event")
    op.drop_table("inference_log")
