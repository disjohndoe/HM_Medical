"""add prescriptions table

Revision ID: 010_prescriptions
Revises: 009_cezih_storno
Create Date: 2026-03-31

"""

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "010_prescriptions"
down_revision: str | None = "009_cezih_storno"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prescriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("patient_id", UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("doktor_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("medical_record_id", UUID(as_uuid=True), sa.ForeignKey("medical_records.id"), nullable=True),
        sa.Column("lijekovi", JSONB, nullable=False),
        sa.Column("cezih_sent", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("cezih_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cezih_recept_id", sa.String(100), nullable=True, index=True),
        sa.Column("cezih_storno", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("cezih_storno_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("napomena", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_prescriptions_patient",
        "prescriptions",
        ["tenant_id", "patient_id", "created_at"],
    )

    # Data migration: copy e-Recept entries from audit_log
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, tenant_id, user_id, resource_id, details, created_at "
            "FROM audit_log "
            "WHERE action = 'e_recept_send' AND resource_type = 'cezih' "
            "ORDER BY created_at"
        )
    ).fetchall()

    for row in rows:
        try:
            details = json.loads(row.details) if isinstance(row.details, str) else row.details
        except (json.JSONDecodeError, TypeError):
            continue

        recept_id = details.get("recept_id", "")
        drug_names = details.get("lijekovi", [])
        lijekovi_json = [
            {"naziv": name, "atk": "", "oblik": "", "jacina": "", "kolicina": 1, "doziranje": "", "napomena": ""}
            for name in drug_names
        ]

        patient_id = row.resource_id
        if not patient_id:
            patient_id_str = details.get("patient_id")
            if patient_id_str:
                patient_id = uuid.UUID(patient_id_str)
            else:
                continue

        conn.execute(
            sa.text(
                "INSERT INTO prescriptions (id, tenant_id, patient_id, doktor_id, lijekovi, "
                "cezih_sent, cezih_sent_at, cezih_recept_id, cezih_storno, napomena, created_at, updated_at) "
                "VALUES (:id, :tenant_id, :patient_id, :doktor_id, :lijekovi, "
                "true, :sent_at, :recept_id, false, :napomena, :created_at, :created_at)"
            ),
            {
                "id": str(uuid.uuid4()),
                "tenant_id": str(row.tenant_id),
                "patient_id": str(patient_id),
                "doktor_id": str(row.user_id) if row.user_id else str(row.tenant_id),
                "lijekovi": json.dumps(lijekovi_json),
                "sent_at": row.created_at,
                "recept_id": recept_id,
                "napomena": "Migrirano iz audit loga",
                "created_at": row.created_at,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_prescriptions_patient", table_name="prescriptions")
    op.drop_table("prescriptions")
