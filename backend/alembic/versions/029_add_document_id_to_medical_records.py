"""add document_id FK to medical_records

Revision ID: 029_record_document
Revises: 028_cezih_signing_method
Create Date: 2026-04-16

Links a medical record to its uploaded attachment so the e-Nalaz dispatcher
can embed the file as a Binary resource in the ITI-65 bundle.
"""

import sqlalchemy as sa

from alembic import op

revision = "029_record_document"
down_revision = "028_cezih_signing_method"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "medical_records",
        sa.Column("document_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_medical_records_document_id",
        "medical_records",
        "documents",
        ["document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_medical_records_document_id",
        "medical_records",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_medical_records_document_id", table_name="medical_records")
    op.drop_constraint("fk_medical_records_document_id", "medical_records", type_="foreignkey")
    op.drop_column("medical_records", "document_id")
