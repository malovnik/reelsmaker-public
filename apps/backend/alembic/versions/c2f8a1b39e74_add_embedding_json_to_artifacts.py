"""add embedding_json to artifacts

Revision ID: c2f8a1b39e74
Revises: 857f16ff0a07
Create Date: 2026-04-19 12:00:00.000000

T6.1 — Cosine retrieval preference memory. Добавляет nullable JSON-колонку
``embedding_json`` в ``artifacts``. Хранит 256-dim Gemini embedding hook-фразы
лайкнутого рилса для семантического retrieval в preference_memory.

Колонка nullable, default None — исторические лайки до T6.1 продолжают
работать через legacy top-by-date fallback. Заполняется только при
проставлении ``meta['liked'] == 'like'`` через like-endpoint.

SQLite поддерживает JSON-колонку (как в ``meta``), отдельной инфраструктуры
не требуется. При <500 лайках linear numpy scan — adequately fast.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c2f8a1b39e74"
down_revision: str | Sequence[str] | None = "857f16ff0a07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("artifacts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "embedding_json",
                sa.JSON(),
                nullable=True,
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("artifacts", schema=None) as batch_op:
        batch_op.drop_column("embedding_json")
