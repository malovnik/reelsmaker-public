"""add custom_system_prompt to jobs

Revision ID: d1a4f6b8e2c5
Revises: c2f8a1b39e74
Create Date: 2026-04-20 12:00:00.000000

Опциональный per-job доп-промпт, заполняемый пользователем в UploadWizard.
Если непустой — прикрепляется в самое начало system-prompt всех LLM-вызовов
(через ``prompts.build_system_prompt``). NULL/"" → поведение без изменений.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d1a4f6b8e2c5"
down_revision: Union[str, Sequence[str], None] = "c2f8a1b39e74"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("custom_system_prompt", sa.Text(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("custom_system_prompt")
