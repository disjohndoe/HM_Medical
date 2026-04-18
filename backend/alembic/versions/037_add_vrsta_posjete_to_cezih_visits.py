"""Add vrsta_posjete column to cezih_visits

Revision ID: 037_vrsta_posjete
Revises: 036_expand_putovnica
Create Date: 2026-04-18

CEZIH QEDm strips Encounter.type on read — vrsta_posjete must be
persisted in our local mirror to survive page reloads.
"""

import sqlalchemy as sa

from alembic import op

revision = "037_vrsta_posjete"
down_revision = "036_expand_putovnica"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cezih_visits",
        sa.Column("vrsta_posjete", sa.String(10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cezih_visits", "vrsta_posjete")
