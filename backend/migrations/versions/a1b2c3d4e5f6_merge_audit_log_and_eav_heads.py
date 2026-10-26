"""Merge audit_log and EAV migration heads.

Revision ID: a1b2c3d4e5f6
Revises: 4566b47c3298, bd85005f9ed6
Create Date: 2026-10-12

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: tuple[str, str] = ("4566b47c3298", "bd85005f9ed6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
