"""split_main_companion_fit_modes

Revision ID: 9df22144281d
Revises: e3f2c8a4d715
Create Date: 2026-04-20 19:47:57.912964

Заменяет единый ``split_screen_mode`` на два независимых поля:
``split_screen_main_fit_mode`` и ``split_screen_companion_fit_mode``.
Старое значение ``'custom'`` переименовано в ``'manual'`` — точнее
отражает семантику (юзер руками двигает/резизит панели).

Data migration: каждое из двух новых полей получает значение старого
``split_screen_mode`` (с заменой 'custom' → 'manual'). После этого
старая колонка удаляется.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9df22144281d"
down_revision: Union[str, Sequence[str], None] = "e3f2c8a4d715"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("post_production_presets", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "split_screen_main_fit_mode",
                sa.String(length=16),
                server_default="fill",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "split_screen_companion_fit_mode",
                sa.String(length=16),
                server_default="fill",
                nullable=False,
            )
        )

    op.execute(
        """
        UPDATE post_production_presets
        SET split_screen_main_fit_mode = CASE
                WHEN split_screen_mode = 'custom' THEN 'manual'
                ELSE split_screen_mode
            END,
            split_screen_companion_fit_mode = CASE
                WHEN split_screen_mode = 'custom' THEN 'manual'
                ELSE split_screen_mode
            END
        """
    )

    with op.batch_alter_table("post_production_presets", schema=None) as batch_op:
        batch_op.drop_column("split_screen_mode")


def downgrade() -> None:
    """Downgrade schema.

    Восстанавливает единый ``split_screen_mode``, предпочитая значение
    ``split_screen_main_fit_mode`` (если они разошлись — редкий кейс после
    редактирования через новый UI). 'manual' → 'custom' для совместимости
    со старым enum.
    """
    with op.batch_alter_table("post_production_presets", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "split_screen_mode",
                sa.String(length=16),
                server_default="fill",
                nullable=False,
            )
        )

    op.execute(
        """
        UPDATE post_production_presets
        SET split_screen_mode = CASE
                WHEN split_screen_main_fit_mode = 'manual' THEN 'custom'
                ELSE split_screen_main_fit_mode
            END
        """
    )

    with op.batch_alter_table("post_production_presets", schema=None) as batch_op:
        batch_op.drop_column("split_screen_companion_fit_mode")
        batch_op.drop_column("split_screen_main_fit_mode")
