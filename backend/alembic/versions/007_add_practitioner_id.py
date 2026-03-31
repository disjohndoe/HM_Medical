"""add practitioner_id to users

Revision ID: 007_practitioner_id
Revises: 006_perm_roles
Create Date: 2026-03-31

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "007_practitioner_id"
down_revision: str | None = "006_perm_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("practitioner_id", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "practitioner_id")
