"""add seen state to chat messages

Revision ID: 20260420_0005
Revises: 20260420_0004
Create Date: 2026-04-20 16:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260420_0005"
down_revision = "20260420_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "seen_at")
