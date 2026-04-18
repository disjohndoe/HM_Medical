"""add cezih_document_oid to medical_records

Revision ID: 038
Revises: 037
"""
from alembic import op
import sqlalchemy as sa

revision = "038"
down_revision = "037"


def upgrade() -> None:
    op.add_column("medical_records", sa.Column("cezih_document_oid", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("medical_records", "cezih_document_oid")
