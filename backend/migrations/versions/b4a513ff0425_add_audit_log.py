"""add_audit_log

Revision ID: b4a513ff0425
Revises: bd85005f9ed6
Create Date: 2026-10-19 01:11:18.268902

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b4a513ff0425"
down_revision: str | Sequence[str] | None = "bd85005f9ed6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_membership_id", sa.Integer(), nullable=True),
        sa.Column("actor_person_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("summary", sa.String(), nullable=False),
        sa.Column("diff", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Append-only enforcement via triggers (spec data-model.md §audit_log).
    op.execute("""
        CREATE FUNCTION audit_log_block_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only';
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER audit_log_no_update_or_delete
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_log_block_mutation();
    """)
    op.execute("ALTER TABLE audit_log ENABLE ALWAYS TRIGGER audit_log_no_update_or_delete;")
    op.execute("""
        CREATE TRIGGER audit_log_no_truncate
        BEFORE TRUNCATE ON audit_log
        FOR EACH STATEMENT EXECUTE FUNCTION audit_log_block_mutation();
    """)
    op.execute("ALTER TABLE audit_log ENABLE ALWAYS TRIGGER audit_log_no_truncate;")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_truncate ON audit_log;")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update_or_delete ON audit_log;")
    op.execute("DROP FUNCTION IF EXISTS audit_log_block_mutation;")
    op.drop_table("audit_log")
