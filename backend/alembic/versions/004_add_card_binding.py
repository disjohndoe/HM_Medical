"""add card binding fields to users

Revision ID: 004_card_binding
Revises: 003_rename_lokacija
Create Date: 2026-03-28

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_card_binding"
down_revision: str | None = "003_rename_lokacija"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("card_holder_name", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("card_certificate_oib", sa.String(length=11), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "card_certificate_oib")
    op.drop_column("users", "card_holder_name")
