"""add target_reel_count to jobs

Revision ID: 4b2e9f7c1a3d
Revises: 199a04cb840f
Create Date: 2026-04-17 15:30:00.000000

Добавляет пользовательский override кол-ва рилсов (5-30) в таблицу jobs.
NULL = auto-target по длительности источника (эмпирика OpusClip).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b2e9f7c1a3d"
down_revision: Union[str, Sequence[str], None] = "199a04cb840f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("target_reel_count", sa.Integer(), nullable=True)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("target_reel_count")
