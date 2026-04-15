"""add user email verification

Revision ID: 20260415_0002
Revises: 20260415_0001
Create Date: 2026-04-15 00:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260415_0002"
down_revision = "20260415_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "email_verified")
