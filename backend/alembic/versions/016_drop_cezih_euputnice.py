"""drop cezih_euputnice table

Revision ID: 016_drop_cezih_euputnice
Revises: 015_preporucena_terapija
Create Date: 2026-04-01

Feature removed — e-Uputnice were never used in production and all
application code referencing the table has been deleted.
"""

import sqlalchemy as sa

from alembic import op

revision = "016_drop_cezih_euputnice"
down_revision = "015_preporucena_terapija"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_cezih_euputnice_external_id", table_name="cezih_euputnice")
    op.drop_index("ix_cezih_euputnice_tenant_id", table_name="cezih_euputnice")
    op.drop_table("cezih_euputnice")


def downgrade() -> None:
    op.create_table(
        "cezih_euputnice",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("external_id", sa.String(length=50), nullable=False),
        sa.Column("datum_izdavanja", sa.String(length=20), nullable=False),
        sa.Column("izdavatelj", sa.String(length=200), nullable=False),
        sa.Column("svrha", sa.String(length=200), nullable=False),
        sa.Column("specijalist", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cezih_euputnice_external_id", "cezih_euputnice", ["external_id"])
    op.create_index("ix_cezih_euputnice_tenant_id", "cezih_euputnice", ["tenant_id"])
