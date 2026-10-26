"""lc_state_fk_and_person_timezone

`lc.state` must be a known state (spec §4.1), so it becomes a foreign key to
`state_timezone`. `person.timezone` (spec §4) is derived from the LC of the
person's most recent membership. Existing people default to Sydney/Melbourne
time, which is also what the app falls back to when an LC has no state.

Revision ID: c7d2e9a41b36
Revises: ae6e461ef689
Create Date: 2026-10-27 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7d2e9a41b36"
down_revision: str | Sequence[str] | None = "ae6e461ef689"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TIMEZONE = "Australia/Melbourne"


def upgrade() -> None:
    op.create_foreign_key(
        "fk_lc_state_state_timezone", "lc", "state_timezone", ["state"], ["state"]
    )
    op.add_column(
        "person",
        sa.Column(
            "timezone",
            sa.String(),
            nullable=False,
            server_default=DEFAULT_TIMEZONE,
        ),
    )


def downgrade() -> None:
    op.drop_column("person", "timezone")
    op.drop_constraint("fk_lc_state_state_timezone", "lc", type_="foreignkey")
