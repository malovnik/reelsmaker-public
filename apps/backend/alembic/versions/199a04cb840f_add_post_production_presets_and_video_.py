"""add post_production presets and video assets

Revision ID: 199a04cb840f
Revises: db8c0fadfc0c
Create Date: 2026-04-16 17:57:51.828851

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '199a04cb840f'
down_revision: Union[str, Sequence[str], None] = 'db8c0fadfc0c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "video_assets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("duration_sec", sa.Float(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("fps", sa.Float(), nullable=False),
        sa.Column("video_codec", sa.String(length=32), nullable=False),
        sa.Column("audio_codec", sa.String(length=32), nullable=True),
        sa.Column("sample_rate", sa.Integer(), nullable=True),
        sa.Column("channels", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_hash", name="uq_video_assets_file_hash"),
    )
    op.create_table(
        "post_production_presets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("intro_asset_id", sa.Integer(), nullable=True),
        sa.Column("outro_asset_id", sa.Integer(), nullable=True),
        sa.Column(
            "audio_normalize_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "audio_target_lufs",
            sa.Float(),
            nullable=False,
            server_default=sa.text("-14.0"),
        ),
        sa.Column(
            "zoom_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "zoom_close_percent",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
        sa.Column(
            "zoom_medium_percent",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("15"),
        ),
        sa.Column(
            "zoom_wide_percent",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "zoom_apply_every_nth_cut",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "zoom_min_interval_sec",
            sa.Float(),
            nullable=False,
            server_default=sa.text("5.0"),
        ),
        sa.Column(
            "zoom_long_segment_threshold_sec",
            sa.Float(),
            nullable=False,
            server_default=sa.text("6.0"),
        ),
        sa.Column(
            "zoom_subsegment_min_sec",
            sa.Float(),
            nullable=False,
            server_default=sa.text("4.0"),
        ),
        sa.Column(
            "zoom_subsegment_max_sec",
            sa.Float(),
            nullable=False,
            server_default=sa.text("7.0"),
        ),
        sa.Column(
            "zoom_alternating_planes_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.ForeignKeyConstraint(
            ["intro_asset_id"],
            ["video_assets.id"],
            name="fk_post_production_presets_intro_asset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["outro_asset_id"],
            ["video_assets.id"],
            name="fk_post_production_presets_outro_asset",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_post_production_presets_name"),
    )
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("post_production_preset_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("post_production_config_json", sa.JSON(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_jobs_post_production_preset",
            "post_production_presets",
            ["post_production_preset_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_jobs_post_production_preset", type_="foreignkey"
        )
        batch_op.drop_column("post_production_config_json")
        batch_op.drop_column("post_production_preset_id")

    op.drop_table("post_production_presets")
    op.drop_table("video_assets")
