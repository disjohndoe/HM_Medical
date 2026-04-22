"""add biljeske table and deactivate non-CEZIH record types

Revision ID: 023_add_biljeske
Revises: 022_clear_stale_trial_expires
Create Date: 2026-04-07
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "023_add_biljeske"
down_revision = "022_clear_stale_trial_expires"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "biljeske",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("doktor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("datum", sa.Date(), nullable=False),
        sa.Column("naslov", sa.String(200), nullable=False),
        sa.Column("sadrzaj", sa.Text(), nullable=False),
        sa.Column("kategorija", sa.String(30), nullable=False, server_default="opca"),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "kategorija IN ('opca', 'anamneza', 'dijagnoza', 'terapija', 'napredak', 'ostalo')",
            name="ck_biljeska_kategorija",
        ),
    )
    op.create_index(
        "ix_biljeske_tenant_patient",
        "biljeske",
        ["tenant_id", "patient_id", "datum"],
    )

    # Deactivate non-CEZIH record types — these are now handled by biljeske
    # Also deactivate unverified CEZIH types until certification confirms them
    op.execute("""
        UPDATE record_types
        SET is_active = false
        WHERE slug IN (
            'dijagnoza', 'misljenje', 'preporuka', 'anamneza',
            'ambulantno_izvjesce', 'otpusno_pismo', 'epikriza'
        )
          AND is_active = true
    """)


def downgrade() -> None:
    # Reactivate record types
    op.execute("""
        UPDATE record_types
        SET is_active = true
        WHERE slug IN (
            'dijagnoza', 'misljenje', 'preporuka', 'anamneza',
            'ambulantno_izvjesce', 'otpusno_pismo', 'epikriza'
        )
          AND is_active = false
    """)
    op.drop_index("ix_biljeske_tenant_patient", table_name="biljeske")
    op.drop_table("biljeske")
