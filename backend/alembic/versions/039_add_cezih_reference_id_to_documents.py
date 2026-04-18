"""add cezih_reference_id to documents

Revision ID: 039
Revises: 038
"""
from alembic import op
import sqlalchemy as sa

revision = "039_cezih_ref_id"
down_revision = "038_document_oid"


def upgrade() -> None:
    op.add_column("documents", sa.Column("cezih_reference_id", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "cezih_reference_id")
