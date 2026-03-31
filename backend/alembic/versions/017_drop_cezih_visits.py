"""drop cezih_visits table and appointment visit columns

Revision ID: 017_drop_cezih_visits
Revises: 016_drop_cezih_euputnice
Create Date: 2026-04-01

Visit management removed — visits are created automatically by CEZIH
when clinical documents are submitted. All application code referencing
the cezih_visits table and appointment.cezih_visit_id has been deleted.
"""

import sqlalchemy as sa
from alembic import op

revision = "017_drop_cezih_visits"
down_revision = "016_drop_cezih_euputnice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove visit-related columns from appointments
    op.drop_index("ix_appointments_cezih_visit_id", table_name="appointments")
    op.drop_column("appointments", "cezih_visit_id")
    op.drop_column("appointments", "cezih_sync_status")

    # Drop the cezih_visits table
    op.drop_index("ix_cezih_visits_cezih_visit_id", table_name="cezih_visits")
    op.drop_index("ix_cezih_visits_patient_id", table_name="cezih_visits")
    op.drop_index("ix_cezih_visits_tenant_id", table_name="cezih_visits")
    op.drop_table("cezih_visits")


def downgrade() -> None:
    # Recreate cezih_visits table
    op.create_table(
        "cezih_visits",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("patient_mbo", sa.String(length=20), nullable=True),
        sa.Column("cezih_visit_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="in-progress"),
        sa.Column("admission_type", sa.String(length=10), nullable=True),
        sa.Column("period_start", sa.String(length=30), nullable=True),
        sa.Column("period_end", sa.String(length=30), nullable=True),
        sa.Column("diagnosis_case_id", sa.String(length=100), nullable=True),
        sa.Column("appointment_id", sa.UUID(), nullable=True),
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

    # Re-add appointment columns
    op.add_column("appointments", sa.Column("cezih_visit_id", sa.String(length=100), nullable=True))
    op.add_column("appointments", sa.Column("cezih_sync_status", sa.String(length=20), nullable=True))
    op.create_index("ix_appointments_cezih_visit_id", "appointments", ["cezih_visit_id"])
