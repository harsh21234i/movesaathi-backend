"""add incident reports

Revision ID: 20260704_0001
Revises: 20260702_0001
Create Date: 2026-07-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260704_0001"
down_revision: str | Sequence[str] | None = "20260702_0001"
branch_labels = None
depends_on = None


incident_status_enum = postgresql.ENUM(
    "open",
    "reviewing",
    "resolved",
    "dismissed",
    name="incidentstatus",
    create_type=False,
)

incident_severity_enum = postgresql.ENUM(
    "low",
    "medium",
    "high",
    "emergency",
    name="incidentseverity",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        incident_status_enum.create(bind, checkfirst=True)
        incident_severity_enum.create(bind, checkfirst=True)
        incidentstatus: sa.TypeEngine = incident_status_enum
        incidentseverity: sa.TypeEngine = incident_severity_enum
        op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'incident_updated'")
    else:
        incidentstatus = sa.String(length=32)
        incidentseverity = sa.String(length=32)

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
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        incident_severity_enum.drop(bind, checkfirst=True)
        incident_status_enum.drop(bind, checkfirst=True)
