"""kpi_record

Revision ID: bd85005f9ed6
Revises: 5d3d031fed82
Create Date: 2026-09-16 10:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bd85005f9ed6"
down_revision: str | Sequence[str] | None = "5d3d031fed82"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "kpi_record",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("attribute_id", sa.Integer(), nullable=False),
        sa.Column("membership_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("value_number", sa.Numeric(12, 2, asdecimal=False), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "SELF",
                "LEADER",
                "IMPORT",
                "SYSTEM",
                name="kpisource",
                native_enum=False,
                length=10,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["attribute_id"], ["attribute.id"]),
        sa.ForeignKeyConstraint(["membership_id"], ["membership.id"]),
        sa.ForeignKeyConstraint(["recorded_by"], ["membership.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["team.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # spec §10: the index a date-range rollup of one KPI, scoped to a
    # member, needs.
    op.create_index(
        "ix_kpi_record_attribute_membership_period",
        "kpi_record",
        ["attribute_id", "membership_id", "period_start"],
    )
    # spec §10: the other index it names — added here rather than in the
    # initial schema migration, since kpi_record's arrival is what actually
    # starts querying membership this way (LC/function-scoped, date-ranged).
    op.create_index(
        "ix_membership_lc_function_dates",
        "membership",
        ["lc_id", "function_id", "start_date", "end_date"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_membership_lc_function_dates", table_name="membership")
    op.drop_index("ix_kpi_record_attribute_membership_period", table_name="kpi_record")
    op.drop_table("kpi_record")
