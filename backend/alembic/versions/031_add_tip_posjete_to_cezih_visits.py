"""recreate cezih_visits table with tip_posjete column

Revision ID: 031_tip_posjete
Revises: 030_drop_document_id
Create Date: 2026-04-17

Migration 017 dropped cezih_visits when visit management was temporarily
removed. Visit management came back (phase 11) but the table was never
recreated — the CezihVisit ORM model existed against a missing table and
all mirror writes were silently swallowed by try/except. Recreating the
table now, with tip_posjete added so we can persist visit type across
reloads (CEZIH QEDm strips Encounter.type on read).
"""
from alembic import op
import sqlalchemy as sa


revision = "031_tip_posjete"
down_revision = "030_drop_document_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cezih_visits",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("patient_mbo", sa.String(length=20), nullable=False),
        sa.Column("cezih_visit_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="in-progress"),
        sa.Column("admission_type", sa.String(length=10), nullable=True),
        sa.Column("tip_posjete", sa.String(length=10), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("diagnosis_case_id", sa.String(length=100), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cezih_visits_tenant_id", "cezih_visits", ["tenant_id"])
    op.create_index("ix_cezih_visits_patient_id", "cezih_visits", ["patient_id"])
    op.create_index("ix_cezih_visits_cezih_visit_id", "cezih_visits", ["cezih_visit_id"])


def downgrade() -> None:
    op.drop_index("ix_cezih_visits_cezih_visit_id", table_name="cezih_visits")
    op.drop_index("ix_cezih_visits_patient_id", table_name="cezih_visits")
    op.drop_index("ix_cezih_visits_tenant_id", table_name="cezih_visits")
    op.drop_table("cezih_visits")
