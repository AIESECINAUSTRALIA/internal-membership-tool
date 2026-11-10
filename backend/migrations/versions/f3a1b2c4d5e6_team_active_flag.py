"""team_active_flag

Adds `active` column to `team` to support soft-disbanding (spec §1.5).
Existing rows default to TRUE so no historical teams are accidentally hidden.

Revision ID: f3a1b2c4d5e6
Revises: c7d2e9a41b36
Create Date: 2026-11-10 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3a1b2c4d5e6"
down_revision: str | Sequence[str] | None = "c7d2e9a41b36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "team",
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("team", "active")
