"""add incident reports

Revision ID: 20260704_0001
Revises: 20260702_0001
Create Date: 2026-07-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260704_0001"
down_revision: str | Sequence[str] | None = "20260702_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    incidentstatus = sa.Enum("open", "reviewing", "resolved", "dismissed", name="incidentstatus")
    incidentseverity = sa.Enum("low", "medium", "high", "emergency", name="incidentseverity")
    incidentstatus.create(bind, checkfirst=True)
    incidentseverity.create(bind, checkfirst=True)

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'incident_updated'")

    op.create_table(
        "incident_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reporter_id", sa.Integer(), nullable=False),
        sa.Column("ride_id", sa.Integer(), nullable=True),
        sa.Column("booking_id", sa.Integer(), nullable=True),
        sa.Column("ride_request_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=140), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", incidentseverity, nullable=False),
        sa.Column("status", incidentstatus, nullable=False),
        sa.Column("support_notes", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ride_id"], ["rides.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["ride_request_id"], ["ride_requests.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incident_reports_id", "incident_reports", ["id"])
    op.create_index("ix_incident_reports_status_created", "incident_reports", ["status", "created_at"])
    op.create_index("ix_incident_reports_reporter_created", "incident_reports", ["reporter_id", "created_at"])
    op.create_index("ix_incident_reports_ride_status", "incident_reports", ["ride_id", "status"])
    op.create_index("ix_incident_reports_booking_status", "incident_reports", ["booking_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_incident_reports_booking_status", table_name="incident_reports")
    op.drop_index("ix_incident_reports_ride_status", table_name="incident_reports")
    op.drop_index("ix_incident_reports_reporter_created", table_name="incident_reports")
    op.drop_index("ix_incident_reports_status_created", table_name="incident_reports")
    op.drop_index("ix_incident_reports_id", table_name="incident_reports")
    op.drop_table("incident_reports")
    op.execute("DROP TYPE IF EXISTS incidentseverity")
    op.execute("DROP TYPE IF EXISTS incidentstatus")
