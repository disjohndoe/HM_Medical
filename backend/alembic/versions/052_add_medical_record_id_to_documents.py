"""add medical_record_id FK to documents

Revision ID: 052_documents_medical_record_id
Revises: 051_procedures_dts
Create Date: 2026-05-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "052_documents_medical_record_id"
down_revision: str | Sequence[str] | None = "051_procedures_dts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("medical_record_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_documents_medical_record_id",
        "documents",
        "medical_records",
        ["medical_record_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_documents_medical_record_id",
        "documents",
        ["medical_record_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_documents_medical_record_id", table_name="documents")
    op.drop_constraint("fk_documents_medical_record_id", "documents", type_="foreignkey")
    op.drop_column("documents", "medical_record_id")
