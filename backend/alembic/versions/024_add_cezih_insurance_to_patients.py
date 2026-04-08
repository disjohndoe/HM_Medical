"""add CEZIH insurance fields to patients

Revision ID: 024_cezih_insurance
Revises: 023_add_biljeske
Create Date: 2026-04-07
"""
import sqlalchemy as sa

from alembic import op

revision = "024_cezih_insurance"
down_revision = "023_add_biljeske"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("cezih_insurance_status", sa.String(50), nullable=True))
    op.add_column("patients", sa.Column("cezih_insurance_checked_at", sa.DateTime(timezone=True), nullable=True))

    # Fix audit_log.created_at default (was frozen at table creation time)
    op.alter_column("audit_log", "created_at", server_default=sa.text("now()"))


def downgrade() -> None:
    op.drop_column("patients", "cezih_insurance_checked_at")
    op.drop_column("patients", "cezih_insurance_status")
