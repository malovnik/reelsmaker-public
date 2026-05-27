"""add vision_profile to jobs

Revision ID: b1c4f7a9d3e2
Revises: 9e5b1f8a2c04
Create Date: 2026-04-17 19:30:00.000000

Добавляет колонку vision_profile в таблицу jobs. Значения:
talking_head (default), fashion, travel, screencast, custom.

Default talking_head — backward-совместимое поведение для всех
существующих jobs. Auto-detect (PHASE 2.2) может подсказать fashion/travel
по низкому WPM + high face coverage.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b1c4f7a9d3e2"
down_revision: Union[str, Sequence[str], None] = "9e5b1f8a2c04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "vision_profile",
                sa.String(length=24),
                nullable=False,
                server_default="talking_head",
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("vision_profile")
