"""add user role

Revision ID: 20260416_0003
Revises: 20260415_0002
Create Date: 2026-04-16 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260416_0003"
down_revision = "20260415_0002"
branch_labels = None
depends_on = None


user_role_enum = postgresql.ENUM("driver", "passenger", name="userrole", create_type=False)


def upgrade() -> None:
    user_role_enum.create(op.get_bind(), checkfirst=True)
    op.add_column("users", sa.Column("role", user_role_enum, nullable=False, server_default="passenger"))


def downgrade() -> None:
    op.drop_column("users", "role")
    user_role_enum.drop(op.get_bind(), checkfirst=True)
