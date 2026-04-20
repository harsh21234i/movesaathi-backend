"""add lifecycle statuses and notifications

Revision ID: 20260420_0004
Revises: 20260416_0003
Create Date: 2026-04-20 15:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260420_0004"
down_revision = "20260416_0003"
branch_labels = None
depends_on = None


ride_status_enum = postgresql.ENUM(
    "scheduled",
    "full",
    "completed",
    "cancelled",
    name="ridestatus",
    create_type=False,
)

notification_type_enum = postgresql.ENUM(
    "booking_requested",
    "booking_accepted",
    "booking_rejected",
    "booking_cancelled",
    "booking_completed",
    "ride_cancelled",
    name="notificationtype",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    for value in (
        "cancelled_by_passenger",
        "cancelled_by_driver",
        "completed",
    ):
        op.execute(sa.text(f"ALTER TYPE bookingstatus ADD VALUE IF NOT EXISTS '{value}'"))

    ride_status_enum.create(bind, checkfirst=True)
    notification_type_enum.create(bind, checkfirst=True)

    op.add_column(
        "rides",
        sa.Column("status", ride_status_enum, nullable=False, server_default="scheduled"),
    )
    op.execute(
        sa.text(
            """
            UPDATE rides
            SET status = CASE
                WHEN is_active = false THEN 'cancelled'
                WHEN available_seats = 0 THEN 'full'
                ELSE 'scheduled'
            END
            """
        )
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", notification_type_enum, nullable=False),
        sa.Column("title", sa.String(length=140), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_notifications_id"), "notifications", ["id"], unique=False)
    op.create_index(op.f("ix_notifications_recipient_id"), "notifications", ["recipient_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_notifications_recipient_id"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_id"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_column("rides", "status")
    notification_type_enum.drop(op.get_bind(), checkfirst=True)
    ride_status_enum.drop(op.get_bind(), checkfirst=True)
