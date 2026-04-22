"""add CEZIH signature columns to medical_records

Revision ID: 019_add_cezih_signature_columns
Revises: 018_add_record_types_table
Create Date: 2026-04-05

Adds cezih_signature_data (Text) and cezih_signed_at (DateTime) columns
to store the digital signature returned by CEZIH remote signing service.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "019_add_cezih_signature_columns"
down_revision = "018_add_record_types_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("medical_records", sa.Column("cezih_signature_data", sa.Text(), nullable=True))
    op.add_column("medical_records", sa.Column("cezih_signed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("medical_records", "cezih_signed_at")
    op.drop_column("medical_records", "cezih_signature_data")
