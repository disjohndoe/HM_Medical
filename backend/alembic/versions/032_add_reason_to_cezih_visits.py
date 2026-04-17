"""add reason column to cezih_visits

Revision ID: 032_visit_reason
Revises: 031_tip_posjete
Create Date: 2026-04-17

CEZIH QEDm read-back often omits Encounter.reasonCode for visits we created
with a reason, leaving the e-Karton list showing blank rows. Persisting the
reason locally so the merge layer can use it as a fallback when CEZIH returns
nothing.
"""
from alembic import op
import sqlalchemy as sa


revision = "032_visit_reason"
down_revision = "031_tip_posjete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cezih_visits",
        sa.Column("reason", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cezih_visits", "reason")
