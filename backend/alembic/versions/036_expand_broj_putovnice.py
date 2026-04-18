"""Expand broj_putovnice to 50 chars

Revision ID: 036_expand_putovnica
Revises: 035_predracun_stavke_tenant
Create Date: 2026-04-18

HZZO test passports can be up to 43 chars (e.g.
TEST187229207429124774553873810518644589945). Real passports vary by
country too — raising limit to 50 so we never reject valid identifiers.
"""

from alembic import op
import sqlalchemy as sa


revision = "036_expand_putovnica"
down_revision = "035_predracun_stavke_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "patients",
        "broj_putovnice",
        existing_type=sa.String(length=15),
        type_=sa.String(length=50),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "patients",
        "broj_putovnice",
        existing_type=sa.String(length=50),
        type_=sa.String(length=15),
        existing_nullable=True,
    )
