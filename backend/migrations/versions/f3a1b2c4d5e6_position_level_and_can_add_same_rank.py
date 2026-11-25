"""position_level_and_can_add_same_rank

Add `level` ('lc' or 'mc') and `can_add_same_rank` (bool) to the `position`
table (spec §2, §3.4, §3.6). Both are absent from the initial schema; this
migration adds them without touching existing rows so running it on a live DB
is safe. Admins set the values via the Admin console's Positions & functions
screen (spec §2A.2, DEV-0049).

Revision ID: f3a1b2c4d5e6
Revises: c7d2e9a41b36
Create Date: 2026-11-15 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3a1b2c4d5e6"
down_revision: str | Sequence[str] | None = "c7d2e9a41b36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `level` is nullable so existing rows get NULL until an admin corrects them.
    op.add_column("position", sa.Column("level", sa.String(5), nullable=True))
    # `can_add_same_rank` defaults False: existing rows cannot add their own rank
    # until explicitly set.
    op.add_column(
        "position",
        sa.Column(
            "can_add_same_rank",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("position", "can_add_same_rank")
    op.drop_column("position", "level")
