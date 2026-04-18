"""add cezih_document_oid to medical_records

Revision ID: 038
Revises: 037
"""
import sqlalchemy as sa

from alembic import op

revision = "038_document_oid"
down_revision = "037_vrsta_posjete"


def upgrade() -> None:
    op.add_column("medical_records", sa.Column("cezih_document_oid", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("medical_records", "cezih_document_oid")
