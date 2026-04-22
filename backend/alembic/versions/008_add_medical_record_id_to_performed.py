"""add medical_record_id FK to performed_procedures

Revision ID: 008_medical_record_link
Revises: 007_practitioner_id
Create Date: 2026-03-31

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "008_medical_record_link"
down_revision: str | None = "007_practitioner_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "performed_procedures",
        sa.Column("medical_record_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_performed_medical_record",
        "performed_procedures",
        "medical_records",
        ["medical_record_id"],
        ["id"],
    )
    op.create_index(
        "ix_performed_procedures_medical_record",
        "performed_procedures",
        ["medical_record_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_performed_procedures_medical_record", table_name="performed_procedures")
    op.drop_constraint("fk_performed_medical_record", "performed_procedures", type_="foreignkey")
    op.drop_column("performed_procedures", "medical_record_id")
