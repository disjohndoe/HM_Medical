"""add_documents_table

Revision ID: 002_add_documents
Revises: 001_expand_tenant
Create Date: 2026-03-24 20:30:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "002_add_documents"
down_revision = "001_expand_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("naziv", sa.String(255), nullable=False),
        sa.Column("kategorija", sa.String(50), nullable=False, server_default="ostalo"),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "kategorija IN ('nalaz', 'snimka', 'dokument', 'ostalo')",
            name="ck_document_kategorija",
        ),
    )
    op.create_index("ix_documents_tenant_patient", "documents", ["tenant_id", "patient_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_tenant_patient", table_name="documents")
    op.drop_table("documents")
