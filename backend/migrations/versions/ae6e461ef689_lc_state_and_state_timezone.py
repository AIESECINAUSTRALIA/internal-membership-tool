"""lc_state_and_state_timezone

Revision ID: ae6e461ef689
Revises: b4a513ff0425
Create Date: 2026-10-19 01:24:16.994927

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ae6e461ef689"
down_revision: str | Sequence[str] | None = "b4a513ff0425"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_STATE_TIMEZONES = [
    ("NSW", "Australia/Sydney"),
    ("VIC", "Australia/Melbourne"),
    ("QLD", "Australia/Brisbane"),
    ("SA", "Australia/Adelaide"),
    ("WA", "Australia/Perth"),
    ("TAS", "Australia/Hobart"),
    ("ACT", "Australia/Sydney"),
    ("NT", "Australia/Darwin"),
]


def upgrade() -> None:
    op.add_column("lc", sa.Column("state", sa.String(), nullable=True))

    op.create_table(
        "state_timezone",
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("timezone", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("state"),
    )

    op.bulk_insert(
        sa.table(
            "state_timezone",
            sa.column("state", sa.String),
            sa.column("timezone", sa.String),
        ),
        [{"state": s, "timezone": tz} for s, tz in _STATE_TIMEZONES],
    )


def downgrade() -> None:
    op.drop_table("state_timezone")
    op.drop_column("lc", "state")
