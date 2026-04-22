"""add cezih_storno boolean to medical_records

Revision ID: 009_cezih_storno
Revises: 008_medical_record_link
Create Date: 2026-03-31

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "009_cezih_storno"
down_revision: str | None = "008_medical_record_link"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "medical_records",
        sa.Column("cezih_storno", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("medical_records", "cezih_storno")
