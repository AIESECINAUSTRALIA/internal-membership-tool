"""home_chart_default

Revision ID: f006558c355d
Revises: c7d2e9a41b36
Create Date: 2026-10-31 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f006558c355d"
down_revision: str | Sequence[str] | None = "c7d2e9a41b36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "home_chart_default",
        sa.Column("function_id", sa.Integer(), nullable=False),
        sa.Column("attribute_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["function_id"], ["function.id"]),
        sa.ForeignKeyConstraint(["attribute_id"], ["attribute.id"]),
        sa.PrimaryKeyConstraint("function_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("home_chart_default")
