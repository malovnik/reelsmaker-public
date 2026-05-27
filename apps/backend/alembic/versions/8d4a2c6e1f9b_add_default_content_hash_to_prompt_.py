"""add default_content_hash to prompt_settings

Revision ID: 8d4a2c6e1f9b
Revises: 7c1f3a9b5e2d
Create Date: 2026-04-17 18:00:00.000000

Вводит версионирование дефолтных промптов. Поле хранит SHA-256 хеш
содержимого ``DEFAULT_PROMPTS[key]`` на момент последнего сида. Если поле
расходится с хешем текущего дефолта И content-хеш строки равен старому
default-хешу (пользователь не редактировал), seed-логика мигрирует row
к новому тексту автоматически. Иначе edits сохраняются, default-хеш
обновляется (чтобы при следующем изменении дефолта user-edit снова
распознавался корректно).

NULL = legacy row до версионирования. Трактуется как "не модифицировался"
при ближайшем сиде — подхватит новый дефолт.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8d4a2c6e1f9b"
down_revision: str | Sequence[str] | None = "7c1f3a9b5e2d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("prompt_settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("default_content_hash", sa.String(length=64), nullable=True),
        )


def downgrade() -> None:
    with op.batch_alter_table("prompt_settings", schema=None) as batch_op:
        batch_op.drop_column("default_content_hash")
