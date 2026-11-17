"""add expa identity and user sessions

Revision ID: 39a779be658e
Revises: f006558c355d
Create Date: 2026-11-17 17:53:52.829142

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "39a779be658e"
down_revision: str | Sequence[str] | None = "f006558c355d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "person",
        sa.Column("expa_id", sa.String(), nullable=True),
    )
    op.create_unique_constraint("uq_person_expa_id", "person", ["expa_id"])

    op.create_table(
        "user_session",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=True),
        sa.Column("oauth_state_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash"),
        sa.UniqueConstraint("oauth_state_hash"),
    )


def downgrade() -> None:
    op.drop_table("user_session")
    op.drop_constraint("uq_person_expa_id", "person", type_="unique")
    op.drop_column("person", "expa_id")
