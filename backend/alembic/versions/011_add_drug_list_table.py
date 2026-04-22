"""add drug_list table for HALMED sync

Revision ID: 011_drug_list
Revises: 010_prescriptions
Create Date: 2026-03-31

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "011_drug_list"
down_revision: str | None = "010_prescriptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "drug_list",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("atk", sa.String(7), nullable=False, index=True),
        sa.Column("naziv", sa.String(255), nullable=False),
        sa.Column("oblik", sa.String(255), nullable=False, server_default=""),
        sa.Column("jacina", sa.String(255), nullable=False, server_default=""),
        sa.Column("inn", sa.String(255), nullable=False, server_default=""),
        sa.Column("nositelj_odobrenja", sa.String(255), nullable=False, server_default=""),
        sa.Column("s_lij", sa.Integer(), nullable=True),
        sa.Column("s_lio", sa.Integer(), nullable=True),
        sa.Column("hzzo_sifra", sa.String(11), nullable=False, server_default=""),
        sa.Column("aktivan", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
    )
    # Composite index for fast ILIKE search
    op.create_index("ix_drug_list_search", "drug_list", ["aktivan"])
    # GIN trigram index for fast ILIKE (requires pg_trgm extension)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE INDEX ix_drug_list_search_trgm ON drug_list USING gin (search_text gin_trgm_ops)")


def downgrade() -> None:
    op.drop_index("ix_drug_list_search_trgm", table_name="drug_list")
    op.drop_index("ix_drug_list_search", table_name="drug_list")
    op.drop_table("drug_list")
