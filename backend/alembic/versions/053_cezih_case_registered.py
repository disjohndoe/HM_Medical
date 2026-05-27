"""add registered flag to cezih_cases

Distinguishes cases this clinic created on CEZIH (registered=true, local is
authoritative for clinical/verification status) from externally-created cases
mirrored from a CEZIH QEDm read (registered=false, CEZIH-authoritative, not
eligible for visit linking). Every existing mirror row is one we created, so
the column backfills to true.

Revision ID: 053_cezih_case_registered
Revises: 052_documents_medical_record_id
Create Date: 2026-05-27

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "053_cezih_case_registered"
down_revision: str | Sequence[str] | None = "052_documents_medical_record_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cezih_cases",
        sa.Column(
            "registered",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("cezih_cases", "registered")
