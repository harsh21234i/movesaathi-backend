"""use numeric money columns

Revision ID: 20260705_0001
Revises: 20260704_0002
Create Date: 2026-07-05 00:01:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260705_0001"
down_revision: str | Sequence[str] | None = "20260704_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("rides") as batch_op:
        batch_op.alter_column(
            "price_per_seat",
            existing_type=sa.Float(),
            type_=sa.Numeric(10, 2),
            existing_nullable=False,
        )

    with op.batch_alter_table("payments") as batch_op:
        batch_op.alter_column(
            "amount",
            existing_type=sa.Float(),
            type_=sa.Numeric(10, 2),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("payments") as batch_op:
        batch_op.alter_column(
            "amount",
            existing_type=sa.Numeric(10, 2),
            type_=sa.Float(),
            existing_nullable=False,
        )

    with op.batch_alter_table("rides") as batch_op:
        batch_op.alter_column(
            "price_per_seat",
            existing_type=sa.Numeric(10, 2),
            type_=sa.Float(),
            existing_nullable=False,
        )
