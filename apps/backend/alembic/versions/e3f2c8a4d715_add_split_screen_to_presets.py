"""add split_screen columns and companion_asset_id to post_production_presets

Revision ID: e3f2c8a4d715
Revises: d1a4f6b8e2c5
Create Date: 2026-04-20 16:30:00.000000

Добавляет поддержку split-screen рендера в пресеты пост-продакшна:
- companion_asset_id FK на video_assets (хранит companion-видео, как intro/outro).
- split_screen_enabled (default False → backward-compat).
- split_screen_mode: fill|fit|custom (default fill).
- split_screen_ratio: % верхней половины (default 50.0).
- split_screen_transforms_json: JSON blob с main/companion transforms для
  mode='custom'. NULL = дефолтные transforms из Pydantic.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e3f2c8a4d715"
down_revision: Union[str, Sequence[str], None] = "d1a4f6b8e2c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("post_production_presets", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("companion_asset_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "split_screen_enabled",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "split_screen_mode",
                sa.String(length=16),
                nullable=False,
                server_default="fill",
            )
        )
        batch_op.add_column(
            sa.Column(
                "split_screen_ratio",
                sa.Float(),
                nullable=False,
                server_default="50.0",
            )
        )
        batch_op.add_column(
            sa.Column("split_screen_transforms_json", sa.JSON(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_post_production_presets_companion_asset_id",
            "video_assets",
            ["companion_asset_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("post_production_presets", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_post_production_presets_companion_asset_id", type_="foreignkey"
        )
        batch_op.drop_column("split_screen_transforms_json")
        batch_op.drop_column("split_screen_ratio")
        batch_op.drop_column("split_screen_mode")
        batch_op.drop_column("split_screen_enabled")
        batch_op.drop_column("companion_asset_id")
