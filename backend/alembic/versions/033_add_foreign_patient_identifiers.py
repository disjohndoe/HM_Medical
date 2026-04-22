"""add foreign patient identifiers + extend cezih mirror identifier column

Revision ID: 033_foreign_ids
Revises: 032_visit_reason
Create Date: 2026-04-17

Foreign patients registered via PMIR (TC11) have no MBO. CEZIH returns
`jedinstveni-identifikator-pacijenta` and they carry EHIC / putovnica.
Previously we stuffed CEZIH id into mbo (truncated) or napomena (text blob).

Adds dedicated columns so the resolver can build correct FHIR identifier
queries for foreigners, and bumps the mirror tables' patient_mbo column to
fit 50-char jedinstveni-ids (the column now stores whichever identifier value
was used for the CEZIH call, not strictly the MBO).
"""

import sqlalchemy as sa

from alembic import op

revision = "033_foreign_ids"
down_revision = "032_visit_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("broj_putovnice", sa.String(length=15), nullable=True))
    op.add_column("patients", sa.Column("ehic_broj", sa.String(length=20), nullable=True))
    op.add_column("patients", sa.Column("cezih_patient_id", sa.String(length=50), nullable=True))
    op.add_column("patients", sa.Column("drzavljanstvo", sa.String(length=3), nullable=True))
    op.create_unique_constraint(
        "uq_patient_tenant_cezih_id",
        "patients",
        ["tenant_id", "cezih_patient_id"],
    )
    op.create_index(
        "ix_patient_tenant_cezih_id",
        "patients",
        ["tenant_id", "cezih_patient_id"],
    )

    op.alter_column(
        "cezih_visits",
        "patient_mbo",
        existing_type=sa.String(length=20),
        type_=sa.String(length=50),
        existing_nullable=False,
    )
    op.alter_column(
        "cezih_cases",
        "patient_mbo",
        existing_type=sa.String(length=20),
        type_=sa.String(length=50),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "cezih_cases",
        "patient_mbo",
        existing_type=sa.String(length=50),
        type_=sa.String(length=20),
        existing_nullable=False,
    )
    op.alter_column(
        "cezih_visits",
        "patient_mbo",
        existing_type=sa.String(length=50),
        type_=sa.String(length=20),
        existing_nullable=False,
    )

    op.drop_index("ix_patient_tenant_cezih_id", table_name="patients")
    op.drop_constraint("uq_patient_tenant_cezih_id", "patients", type_="unique")
    op.drop_column("patients", "drzavljanstvo")
    op.drop_column("patients", "cezih_patient_id")
    op.drop_column("patients", "ehic_broj")
    op.drop_column("patients", "broj_putovnice")
