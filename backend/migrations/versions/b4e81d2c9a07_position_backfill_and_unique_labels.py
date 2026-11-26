"""position_backfill_and_unique_labels

Three things, all for the Admin console's Positions & functions screen (DEV-0049):

1. **Fill in `level` and `can_add_same_rank`** for the positions spec §2 defines.
   The previous migration (f3a1b2c4d5e6) added both columns empty, so every existing
   position had no level and no president exception.

2. **Fix the ranks.** The original seed stored ranks with "lower number = more senior"
   (LCP = 1). The spec, and all of the permission code, use the opposite: a higher
   number is a higher position (Member = 1 ... MCP = 7). The permission code reads the
   stored rank before its fallback, so the seeded LCP was being treated as ranking no
   higher than a Member. See docs/data-model.md, "Known differences from the spec".

3. **Make names unique, ignoring case**, for both positions and functions, so two
   positions can't both be called "Member" / "member" and confuse every dropdown.

Only rows whose `key` matches are touched; a position an admin added is left alone.
Safe with the previous release: it reads the same columns and gets correct values.

This revision also joins the two heads that existed after merging main
(70fc319bf184 from this branch, 39a779be658e from the EXPA sign-in work), so no
separate merge migration is needed.

Revision ID: b4e81d2c9a07
Revises: 70fc319bf184, 39a779be658e
Create Date: 2026-11-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4e81d2c9a07"
down_revision: str | Sequence[str] | None = ("70fc319bf184", "39a779be658e")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Spec §2: key -> (rank, level, can_add_same_rank). Higher rank = higher position.
SPEC_POSITIONS: dict[str, tuple[int, str, bool]] = {
    "member": (1, "lc", False),
    "team_leader": (2, "lc", False),
    "lcvp": (3, "lc", False),
    "lcp": (4, "lc", True),
    "mcd": (5, "mc", False),
    "mcvp": (6, "mc", False),
    "mcp": (7, "mc", True),
}


def upgrade() -> None:
    update_position = sa.text(
        """
        UPDATE position
        SET rank = :rank, level = :level, can_add_same_rank = :can_add_same_rank
        WHERE key = :key
        """
    )
    for key, (rank, level, can_add_same_rank) in SPEC_POSITIONS.items():
        op.execute(
            update_position.bindparams(
                key=key, rank=rank, level=level, can_add_same_rank=can_add_same_rank
            )
        )

    op.create_index("uq_position_label_lower", "position", [sa.text("lower(label)")], unique=True)
    op.create_index("uq_function_label_lower", "function", [sa.text("lower(label)")], unique=True)


def downgrade() -> None:
    # Only the indexes are undone. The rank/level values are NOT put back: the old
    # inverted ranks were a bug, and restoring them would break the permission code.
    # (Never run a downgrade on prod anyway — see CLAUDE.md.)
    op.drop_index("uq_function_label_lower", table_name="function")
    op.drop_index("uq_position_label_lower", table_name="position")
