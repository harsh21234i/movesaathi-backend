"""add real payment provider foundation

Revision ID: 20260613_0001
Revises: 20260522_0001
Create Date: 2026-06-13 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260613_0001"
down_revision: str | Sequence[str] | None = "20260522_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE paymentprovider ADD VALUE IF NOT EXISTS 'razorpay'")

    with op.batch_alter_table("payments") as batch_op:
        batch_op.add_column(sa.Column("amount_minor", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("provider_order_id", sa.String(length=120), nullable=True))
        batch_op.alter_column("provider_payment_id", existing_type=sa.String(length=120), nullable=True)
        batch_op.drop_column("provider_client_secret")

    op.execute("UPDATE payments SET amount_minor = CAST(ROUND(amount * 100) AS INTEGER)")
    op.execute("UPDATE payments SET provider_order_id = provider_payment_id")

    with op.batch_alter_table("payments") as batch_op:
        batch_op.alter_column("amount_minor", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("provider_order_id", existing_type=sa.String(length=120), nullable=False)
        batch_op.create_unique_constraint("uq_payments_provider_order_id", ["provider_order_id"])


def downgrade() -> None:
    with op.batch_alter_table("payments") as batch_op:
        batch_op.add_column(sa.Column("provider_client_secret", sa.String(length=255), nullable=True))
        batch_op.drop_constraint("uq_payments_provider_order_id", type_="unique")
        batch_op.alter_column("provider_payment_id", existing_type=sa.String(length=120), nullable=False)
        batch_op.drop_column("provider_order_id")
        batch_op.drop_column("amount_minor")
