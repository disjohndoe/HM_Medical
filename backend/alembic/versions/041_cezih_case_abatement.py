"""add abatement_date to cezih_cases for local mirror of resolve/reopen state

Revision ID: 041_cezih_case_abatement
Revises: 040_doctor_identifiers
"""
import sqlalchemy as sa

from alembic import op

revision = "041_cezih_case_abatement"
down_revision = "040_doctor_identifiers"


def upgrade() -> None:
    op.add_column("cezih_cases", sa.Column("abatement_date", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("cezih_cases", "abatement_date")
