"""add driver request dismissals

Revision ID: 20260521_0001
Revises: 20260518_0001_add_dispatch_requests
Create Date: 2026-05-21 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260521_0001"
down_revision: str | None = "20260518_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "driver_request_dismissals",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("ride_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("driver_id", "request_id", name="uq_driver_request_dismissals_driver_request"),
    )
    op.create_index("ix_driver_request_dismissals_request_id", "driver_request_dismissals", ["request_id"])
    op.create_index("ix_driver_request_dismissals_driver_id", "driver_request_dismissals", ["driver_id"])


def downgrade() -> None:
    op.drop_index("ix_driver_request_dismissals_driver_id", table_name="driver_request_dismissals")
    op.drop_index("ix_driver_request_dismissals_request_id", table_name="driver_request_dismissals")
    op.drop_table("driver_request_dismissals")
