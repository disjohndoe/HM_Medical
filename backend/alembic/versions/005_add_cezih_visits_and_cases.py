"""add_cezih_visits_and_cases

Revision ID: 005_cezih_vc
Revises: 004_add_card_binding
Create Date: 2026-03-30

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "005_cezih_vc"
down_revision: str | Sequence[str] | None = "004_card_binding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- cezih_visits ---
    op.create_table(
        "cezih_visits",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("cezih_visit_id", sa.String(length=100), nullable=True, comment="CEZIH-assigned visit identifier"),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("patient_mbo", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="in-progress"),
        sa.Column("admission_type", sa.String(length=10), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("diagnosis_case_id", sa.String(length=100), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cezih_visits_tenant_id", "cezih_visits", ["tenant_id"])
    op.create_index("ix_cezih_visits_patient_id", "cezih_visits", ["patient_id"])
    op.create_index("ix_cezih_visits_cezih_visit_id", "cezih_visits", ["cezih_visit_id"])

    # --- cezih_cases ---
    op.create_table(
        "cezih_cases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "cezih_case_id", sa.String(length=100), nullable=True, comment="CEZIH-assigned global case identifier"
        ),
        sa.Column("local_case_id", sa.String(length=100), nullable=False),
        sa.Column("patient_id", sa.UUID(), nullable=False),
        sa.Column("patient_mbo", sa.String(length=20), nullable=False),
        sa.Column("icd_code", sa.String(length=20), nullable=False),
        sa.Column("icd_display", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("clinical_status", sa.String(length=30), nullable=True),
        sa.Column("verification_status", sa.String(length=30), nullable=False, server_default="unconfirmed"),
        sa.Column("onset_date", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cezih_cases_tenant_id", "cezih_cases", ["tenant_id"])
    op.create_index("ix_cezih_cases_patient_id", "cezih_cases", ["patient_id"])
    op.create_index("ix_cezih_cases_cezih_case_id", "cezih_cases", ["cezih_case_id"])
    op.create_index("ix_cezih_cases_local_case_id", "cezih_cases", ["local_case_id"])


def downgrade() -> None:
    op.drop_index("ix_cezih_cases_local_case_id", table_name="cezih_cases")
    op.drop_index("ix_cezih_cases_cezih_case_id", table_name="cezih_cases")
    op.drop_index("ix_cezih_cases_patient_id", table_name="cezih_cases")
    op.drop_index("ix_cezih_cases_tenant_id", table_name="cezih_cases")
    op.drop_table("cezih_cases")

    op.drop_index("ix_cezih_visits_cezih_visit_id", table_name="cezih_visits")
    op.drop_index("ix_cezih_visits_patient_id", table_name="cezih_visits")
    op.drop_index("ix_cezih_visits_tenant_id", table_name="cezih_visits")
    op.drop_table("cezih_visits")
