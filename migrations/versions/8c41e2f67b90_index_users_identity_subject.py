"""Índice para resolução da identidade autenticada sem seletor de empresa.

Revision ID: 8c41e2f67b90
Revises: 2bfff13426c5
"""

from alembic import op

revision: str = "8c41e2f67b90"
down_revision: str | None = "2bfff13426c5"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_index("ix_users_identity_subject", "users", ["identity_subject"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_identity_subject", table_name="users")
