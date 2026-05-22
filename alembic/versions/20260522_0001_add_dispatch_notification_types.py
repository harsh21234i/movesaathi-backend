"""add dispatch notification types

Revision ID: 20260522_0001
Revises: 20260521_0001
Create Date: 2026-05-22 00:01:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260522_0001"
down_revision: str | Sequence[str] | None = "20260521_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'dispatch_matched'")
        op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'dispatch_cancelled'")
        op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'dispatch_expired'")


def downgrade() -> None:
    pass
