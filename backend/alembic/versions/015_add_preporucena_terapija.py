"""add preporucena_terapija JSONB column to medical_records

Revision ID: 015_preporucena_terapija
Revises: 014_add_cezih_link_to_appointments
Create Date: 2026-03-31

Stores structured drug recommendations within the clinical finding (e-Nalaz).
Private practitioners include therapy recommendations in their e-Nalaz so
the family doctor can issue an e-Recept with RS (preporuka specijalista) code.
"""

import sqlalchemy as sa

from alembic import op

revision = "015_preporucena_terapija"
down_revision = "014_cezih_apt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "medical_records",
        sa.Column("preporucena_terapija", sa.JSON, nullable=True, server_default=sa.text("null")),
    )


def downgrade() -> None:
    op.drop_column("medical_records", "preporucena_terapija")
