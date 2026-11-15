"""merge_home_chart_and_position_columns

Revision ID: 70fc319bf184
Revises: f006558c355d, f3a1b2c4d5e6
Create Date: 2026-11-15 07:25:26.918508

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "70fc319bf184"
down_revision: str | Sequence[str] | None = ("f006558c355d", "f3a1b2c4d5e6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
