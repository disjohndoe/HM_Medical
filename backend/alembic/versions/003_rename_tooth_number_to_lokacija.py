"""rename tooth_number to lokacija

Revision ID: 003_rename_lokacija
Revises: b9d406b44dcc
Create Date: 2026-03-27

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_rename_lokacija"
down_revision: str | None = "b9d406b44dcc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("performed_procedures", sa.Column("lokacija", sa.String(length=100), nullable=True))
    op.drop_column("performed_procedures", "tooth_number")


def downgrade() -> None:
    op.add_column("performed_procedures", sa.Column("tooth_number", sa.Integer(), nullable=True))
    op.drop_column("performed_procedures", "lokacija")
