"""attribute catalog

Revision ID: 5d3d031fed82
Revises: 0b11f06365cd
Create Date: 2026-09-16 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5d3d031fed82"
down_revision: str | Sequence[str] | None = "0b11f06365cd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "attribute",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column(
            "applies_to",
            sa.Enum(
                "PERSON",
                "MEMBERSHIP",
                "KPI",
                name="attributeappliesto",
                native_enum=False,
                length=20,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "data_type",
            sa.Enum(
                "TEXT",
                "NUMBER",
                "DATE",
                "BOOLEAN",
                "ENUM",
                name="attributedatatype",
                native_enum=False,
                length=10,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("unit", sa.String(), nullable=True),
        sa.Column("enum_options", sa.JSON(), nullable=True),
        sa.Column("validation", sa.JSON(), nullable=True),
        sa.Column("function_id", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("term_introduced_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["function_id"], ["function.id"]),
        sa.ForeignKeyConstraint(["term_introduced_id"], ["term.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_attribute_key"), "attribute", ["key"], unique=True)

    op.create_table(
        "attribute_value",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("attribute_id", sa.Integer(), nullable=False),
        sa.Column(
            "entity_type",
            sa.Enum(
                "PERSON",
                "MEMBERSHIP",
                name="attributeentitytype",
                native_enum=False,
                length=10,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("value_text", sa.String(), nullable=True),
        sa.Column("value_number", sa.Numeric(12, 2, asdecimal=False), nullable=True),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("value_bool", sa.Boolean(), nullable=True),
        sa.Column("recorded_by", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["attribute_id"], ["attribute.id"]),
        sa.ForeignKeyConstraint(["recorded_by"], ["membership.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_type",
            "entity_id",
            "attribute_id",
            name="uq_attribute_value_entity_attribute",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("attribute_value")
    op.drop_index(op.f("ix_attribute_key"), table_name="attribute")
    op.drop_table("attribute")
