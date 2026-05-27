"""add bw_enabled to post_production_presets

Revision ID: 7c1f3a9b5e2d
Revises: 4b2e9f7c1a3d
Create Date: 2026-04-17 16:00:00.000000

Первый video effect в новом plugin-registry (services/video_effects/).
Флаг false по умолчанию — не влияет на существующие пресеты.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c1f3a9b5e2d"
down_revision: Union[str, Sequence[str], None] = "4b2e9f7c1a3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("post_production_presets", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "bw_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("post_production_presets", schema=None) as batch_op:
        batch_op.drop_column("bw_enabled")
