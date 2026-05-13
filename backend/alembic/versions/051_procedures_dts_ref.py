"""add dts_code reference to procedures table

Link procedures to DTS codes. Old sifra/naziv/kategorija kept for
backward compat; new rows auto-populate from DTS data.

Revision ID: 051_procedures_dts
Revises: 050_dts_codes
"""

import sqlalchemy as sa

from alembic import op

revision = "051_procedures_dts"
down_revision = "050_dts_codes"


def upgrade() -> None:
    op.add_column("procedures", sa.Column("dts_code_id", sa.UUID(), nullable=True))
    op.add_column("procedures", sa.Column("dts_code", sa.String(20), nullable=True))
    op.create_foreign_key("fk_procedures_dts_code_id", "procedures", "dts_codes", ["dts_code_id"], ["id"])
    op.create_unique_constraint("uq_procedure_tenant_dts_code", "procedures", ["tenant_id", "dts_code"])


def downgrade() -> None:
    op.drop_constraint("uq_procedure_tenant_dts_code", "procedures", type_="unique")
    op.drop_constraint("fk_procedures_dts_code_id", "procedures", type_="foreignkey")
    op.drop_column("procedures", "dts_code")
    op.drop_column("procedures", "dts_code_id")
