"""merge_home_chart_and_position_columns

Revision ID: 70fc319bf184
Revises: f006558c355d, f3a1b2c4d5e6
Create Date: 2026-11-15 07:25:26.918508

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '70fc319bf184'
down_revision: Union[str, Sequence[str], None] = ('f006558c355d', 'f3a1b2c4d5e6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
