"""add dispatch request tables

Revision ID: 20260518_0001
Revises: 20260516_0001
Create Date: 2026-05-18 00:01:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260518_0001"
down_revision: str | Sequence[str] | None = "20260516_0001"
branch_labels = None
depends_on = None


ride_request_status = postgresql.ENUM(
    "open",
    "matched",
    "cancelled",
    "expired",
    name="riderequeststatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        ride_request_status.create(bind, checkfirst=True)

    op.create_table(
        "driver_availability",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("heading", sa.Float(), nullable=True),
        sa.Column("is_online", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("driver_id", name="uq_driver_availability_driver_id"),
    )
    op.create_index("ix_driver_availability_online_updated", "driver_availability", ["is_online", "updated_at"])

    op.create_table(
        "ride_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("passenger_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("origin", sa.String(length=120), nullable=False),
        sa.Column("destination", sa.String(length=120), nullable=False),
        sa.Column("origin_latitude", sa.Float(), nullable=False),
        sa.Column("origin_longitude", sa.Float(), nullable=False),
        sa.Column("destination_latitude", sa.Float(), nullable=False),
        sa.Column("destination_longitude", sa.Float(), nullable=False),
        sa.Column("requested_departure_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", ride_request_status, nullable=False),
        sa.Column("matched_driver_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("matched_ride_id", sa.Integer(), sa.ForeignKey("rides.id", ondelete="SET NULL"), nullable=True),
        sa.Column("matched_booking_id", sa.Integer(), sa.ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ride_requests_status_created", "ride_requests", ["status", "created_at"])
    op.create_index("ix_ride_requests_pickup_coords", "ride_requests", ["origin_latitude", "origin_longitude"])


def downgrade() -> None:
    op.drop_index("ix_ride_requests_pickup_coords", table_name="ride_requests")
    op.drop_index("ix_ride_requests_status_created", table_name="ride_requests")
    op.drop_table("ride_requests")
    op.drop_index("ix_driver_availability_online_updated", table_name="driver_availability")
    op.drop_table("driver_availability")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        ride_request_status.drop(bind, checkfirst=True)
