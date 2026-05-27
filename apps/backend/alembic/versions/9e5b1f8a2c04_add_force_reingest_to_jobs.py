"""add force_reingest to jobs

Revision ID: 9e5b1f8a2c04
Revises: 8d4a2c6e1f9b
Create Date: 2026-04-17 18:00:00.000000

Добавляет флаг ``force_reingest`` в таблицу jobs. Когда True — pipeline
инвалидирует transcript cache перед Stage 2 и заново транскрибирует.
По умолчанию False (SHA256-keyed cache используется автоматически).
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "9e5b1f8a2c04"
down_revision: Union[str, Sequence[str], None] = "8d4a2c6e1f9b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "force_reingest",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("force_reingest")
