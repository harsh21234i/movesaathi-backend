"""add payments

Revision ID: 20260514_0009
Revises: 20260504_0008
Create Date: 2026-05-14 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260514_0009"
down_revision: str | Sequence[str] | None = "20260504_0008"
branch_labels = None
depends_on = None


payment_status_enum = postgresql.ENUM(
    "pending",
    "authorized",
    "captured",
    "cancelled",
    "refunded",
    "failed",
    name="paymentstatus",
    create_type=False,
)

payment_provider_enum = postgresql.ENUM(
    "mock",
    name="paymentprovider",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        payment_status_enum.create(bind, checkfirst=True)
        payment_provider_enum.create(bind, checkfirst=True)
        status_type: sa.TypeEngine = payment_status_enum
        provider_type: sa.TypeEngine = payment_provider_enum
    else:
        status_type = sa.String(length=32)
        provider_type = sa.String(length=32)

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payer_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
        sa.Column("status", status_type, nullable=False, server_default="pending"),
        sa.Column("provider", provider_type, nullable=False, server_default="mock"),
        sa.Column("provider_payment_id", sa.String(length=120), nullable=False),
        sa.Column("provider_client_secret", sa.String(length=255), nullable=True),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("booking_id", name="uq_payments_booking_id"),
        sa.UniqueConstraint("provider_payment_id", name="uq_payments_provider_payment_id"),
    )
    op.create_index(op.f("ix_payments_id"), "payments", ["id"], unique=False)
    op.create_index("ix_payments_user_status_created", "payments", ["payer_id", "status", "created_at"], unique=False)
    op.create_index("ix_payments_booking_status", "payments", ["booking_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_payments_booking_status", table_name="payments")
    op.drop_index("ix_payments_user_status_created", table_name="payments")
    op.drop_index(op.f("ix_payments_id"), table_name="payments")
    op.drop_table("payments")
    if op.get_bind().dialect.name == "postgresql":
        payment_provider_enum.drop(op.get_bind(), checkfirst=True)
        payment_status_enum.drop(op.get_bind(), checkfirst=True)
