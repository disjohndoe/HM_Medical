"""add cezih_encounter_id and cezih_case_id to medical_records

Revision ID: a1b2c3d4e5f6
Revises: b9d406b44dcc
Create Date: 2026-04-13

"""
import sqlalchemy as sa

from alembic import op

revision = 'a1b2c3d4e5f6'
down_revision = '024_cezih_insurance'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('medical_records', sa.Column('cezih_encounter_id', sa.String(100), nullable=True))
    op.add_column('medical_records', sa.Column('cezih_case_id', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('medical_records', 'cezih_case_id')
    op.drop_column('medical_records', 'cezih_encounter_id')
