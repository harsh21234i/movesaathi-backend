"""merge payments and location heads

Revision ID: 20260516_0001
Revises: 20260514_0009, 20260514_0010
Create Date: 2026-05-16 00:01:00.000000
"""

from collections.abc import Sequence

revision: str = "20260516_0001"
down_revision: str | Sequence[str] | None = ("20260514_0009", "20260514_0010")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
