"""add CEZIH link columns to appointments

Revision ID: 014_cezih_apt
Revises: 013_hzzo_contract
Create Date: 2026-03-31

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "014_cezih_apt"
down_revision: str | None = "013_hzzo_contract"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("cezih_visit_id", sa.String(100), nullable=True,
                  comment="CEZIH visit identifier linked to this appointment"),
    )
    op.add_column(
        "appointments",
        sa.Column("cezih_sync_status", sa.String(20), nullable=True,
                  comment="CEZIH sync state: pending, synced, failed"),
    )
    op.create_index("ix_appointments_cezih_visit_id", "appointments", ["cezih_visit_id"])

    op.add_column(
        "cezih_visits",
        sa.Column("appointment_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key("fk_cezih_visits_appointment_id", "cezih_visits", "appointments", ["appointment_id"], ["id"])
    op.create_index("ix_cezih_visits_appointment_id", "cezih_visits", ["appointment_id"])


def downgrade() -> None:
    op.drop_index("ix_cezih_visits_appointment_id", table_name="cezih_visits")
    op.drop_constraint("fk_cezih_visits_appointment_id", "cezih_visits", type_="foreignkey")
    op.drop_column("cezih_visits", "appointment_id")

    op.drop_index("ix_appointments_cezih_visit_id", table_name="appointments")
    op.drop_column("appointments", "cezih_sync_status")
    op.drop_column("appointments", "cezih_visit_id")
