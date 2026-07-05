"""add booking share tokens

Revision ID: 20260704_0002
Revises: 20260704_0001
Create Date: 2026-07-04 00:02:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260704_0002"
down_revision: str | Sequence[str] | None = "20260704_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("bookings") as batch_op:
        batch_op.add_column(sa.Column("share_token_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("share_token_created_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("share_token_revoked_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_unique_constraint("uq_bookings_share_token_hash", ["share_token_hash"])


def downgrade() -> None:
    with op.batch_alter_table("bookings") as batch_op:
        batch_op.drop_constraint("uq_bookings_share_token_hash", type_="unique")
        batch_op.drop_column("share_token_revoked_at")
        batch_op.drop_column("share_token_created_at")
        batch_op.drop_column("share_token_hash")
