"""add ride location tracking

Revision ID: 20260514_0010
Revises: 20260504_0008
Create Date: 2026-05-14 00:10:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260514_0010"
down_revision: str | Sequence[str] | None = "20260504_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("rides") as batch_op:
        batch_op.add_column(sa.Column("origin_latitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("origin_longitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("destination_latitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("destination_longitude", sa.Float(), nullable=True))

    op.create_table(
        "ride_locations",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("ride_id", sa.Integer(), sa.ForeignKey("rides.id", ondelete="CASCADE"), nullable=False),
        sa.Column("driver_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("heading", sa.Float(), nullable=True),
        sa.Column("speed_kmph", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("latitude >= -90 AND latitude <= 90", name="ck_ride_locations_latitude_range"),
        sa.CheckConstraint("longitude >= -180 AND longitude <= 180", name="ck_ride_locations_longitude_range"),
    )
    op.create_index(op.f("ix_ride_locations_id"), "ride_locations", ["id"], unique=False)
    op.create_index("ix_ride_locations_ride_created", "ride_locations", ["ride_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ride_locations_ride_created", table_name="ride_locations")
    op.drop_index(op.f("ix_ride_locations_id"), table_name="ride_locations")
    op.drop_table("ride_locations")
    with op.batch_alter_table("rides") as batch_op:
        batch_op.drop_column("destination_longitude")
        batch_op.drop_column("destination_latitude")
        batch_op.drop_column("origin_longitude")
        batch_op.drop_column("origin_latitude")
