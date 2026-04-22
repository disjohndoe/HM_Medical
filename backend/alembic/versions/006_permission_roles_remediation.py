"""permission_roles_remediation

Revision ID: 006_perm_roles
Revises: 005_cezih_vc
Create Date: 2026-03-30

Adds:
- users.card_required column (smart card enforcement)
- medical_records.sensitivity column (record access scope)
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "006_perm_roles"
down_revision: str | Sequence[str] | None = "005_cezih_vc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop patient_doctor_assignments table if it exists (from previous over-engineering)
    op.execute("DROP TABLE IF EXISTS patient_doctor_assignments")

    # --- users.card_required ---
    op.add_column("users", sa.Column("card_required", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    # --- medical_records.sensitivity ---
    op.add_column(
        "medical_records",
        sa.Column("sensitivity", sa.String(20), nullable=False, server_default=sa.text("'standard'")),
    )
    op.create_check_constraint(
        "ck_record_sensitivity",
        "medical_records",
        "sensitivity IN ('standard', 'nursing', 'restricted')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_record_sensitivity", "medical_records", type_="check")
    op.drop_column("medical_records", "sensitivity")
    op.drop_column("users", "card_required")
    # Drop assignment table if it exists
    op.execute("DROP TABLE IF EXISTS patient_doctor_assignments")
