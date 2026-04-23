"""medical_records: add cezih_last_replaced_at

Explicit timestamp set only by successful ITI-65 replace so the UI can render
a "Zamijenjen" state without relying on an updated_at heuristic (which flips
on any PATCH and has a 60s buffer that misses fast edits).

Revision ID: 044_add_cezih_last_replaced_at
Revises: 043_cezih_visits_local_first
"""

import sqlalchemy as sa

from alembic import op

revision = "044_add_cezih_last_replaced_at"
down_revision = "043_cezih_visits_local_first"


def upgrade() -> None:
    op.add_column(
        "medical_records",
        sa.Column("cezih_last_replaced_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("medical_records", "cezih_last_replaced_at")
