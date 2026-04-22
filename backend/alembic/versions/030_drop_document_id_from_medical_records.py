"""drop document_id FK from medical_records (revert 029)

Revision ID: 030_drop_document_id
Revises: 029_record_document
Create Date: 2026-04-16

029 was a mistake — targeted the wrong popup. Rolling back the column so
the DB is clean for the real work (different popup, TBD).
"""

import sqlalchemy as sa

from alembic import op

revision = "030_drop_document_id"
down_revision = "029_record_document"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_medical_records_document_id", table_name="medical_records")
    op.drop_constraint("fk_medical_records_document_id", "medical_records", type_="foreignkey")
    op.drop_column("medical_records", "document_id")


def downgrade() -> None:
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
