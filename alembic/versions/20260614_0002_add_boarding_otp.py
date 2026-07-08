"""add boarding otp verification

Revision ID: 20260614_0002
Revises: 20260613_0001
Create Date: 2026-06-14 12:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260614_0002"
down_revision: str | Sequence[str] | None = "20260613_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("bookings") as batch_op:
        batch_op.add_column(sa.Column("boarding_otp_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("boarding_otp_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("boarded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bookings") as batch_op:
        batch_op.drop_column("boarded_at")
        batch_op.drop_column("boarding_otp_expires_at")
        batch_op.drop_column("boarding_otp_hash")
