"""add tip_posjete to cezih_visits mirror

Revision ID: 031_tip_posjete
Revises: 030_drop_document_id
Create Date: 2026-04-17

CEZIH QEDm strips Encounter.type on read, so tip_posjete never comes back
from the list endpoint. The local mirror is the only authoritative source
for this field after a visit is created/edited.
"""
from alembic import op
import sqlalchemy as sa


revision = "031_tip_posjete"
down_revision = "030_drop_document_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cezih_visits",
        sa.Column("tip_posjete", sa.String(length=10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cezih_visits", "tip_posjete")
