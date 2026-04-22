"""add has_hzzo_contract flag to tenants

Revision ID: 013_hzzo_contract
Revises: 012_hzzo_drugs
Create Date: 2026-03-31

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "013_hzzo_contract"
down_revision: str | None = "012_hzzo_drugs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("has_hzzo_contract", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # Backfill: tenants with a šifra ustanove likely have an HZZO contract
    op.execute("UPDATE tenants SET has_hzzo_contract = true WHERE sifra_ustanove IS NOT NULL AND sifra_ustanove != ''")


def downgrade() -> None:
    op.drop_column("tenants", "has_hzzo_contract")
