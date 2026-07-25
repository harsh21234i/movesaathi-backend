"""add driver verification profile

Revision ID: 20260702_0001
Revises: 20260614_0002
Create Date: 2026-07-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260702_0001"
down_revision: str | Sequence[str] | None = "20260614_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    driver_verification_status = sa.Enum(
        "not_required",
        "pending",
        "verified",
        "rejected",
        name="driververificationstatus",
    )
    driver_verification_status.create(bind, checkfirst=True)

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'driver_verification_approved'")
        op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'driver_verification_rejected'")

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "driver_verification_status",
                driver_verification_status,
                nullable=False,
                server_default="not_required",
            )
        )
        batch_op.add_column(sa.Column("vehicle_make", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("vehicle_model", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("vehicle_color", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("vehicle_plate_number", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("driver_license_number", sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column("driver_verification_rejection_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("driver_profile_submitted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("driver_profile_reviewed_at", sa.DateTime(timezone=True), nullable=True))

    op.execute("UPDATE users SET driver_verification_status = 'pending' WHERE role = 'driver'")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("driver_profile_reviewed_at")
        batch_op.drop_column("driver_profile_submitted_at")
        batch_op.drop_column("driver_verification_rejection_reason")
        batch_op.drop_column("driver_license_number")
        batch_op.drop_column("vehicle_plate_number")
        batch_op.drop_column("vehicle_color")
        batch_op.drop_column("vehicle_model")
        batch_op.drop_column("vehicle_make")
        batch_op.drop_column("driver_verification_status")

    op.execute("DROP TYPE IF EXISTS driververificationstatus")
