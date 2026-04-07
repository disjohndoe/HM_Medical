"""add predracun tables

Revision ID: 021
Revises: 020
Create Date: 2026-04-05
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "021_add_predracun_tables"
down_revision = "020_add_account_lockout_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "predracun_counters",
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("next_seq", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("tenant_id", "year"),
    )

    op.create_table(
        "predracuni",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("patient_id", UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("broj", sa.String(20), nullable=False),
        sa.Column("datum", sa.Date(), nullable=False),
        sa.Column("ukupno_cents", sa.Integer(), nullable=False),
        sa.Column("napomena", sa.Text(), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_predracun_broj_tenant", "predracuni", ["tenant_id", "broj"])
    op.create_index("ix_predracuni_patient", "predracuni", ["tenant_id", "patient_id", "datum"])

    op.create_table(
        "predracun_stavke",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "predracun_id",
            UUID(as_uuid=True),
            sa.ForeignKey("predracuni.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "performed_procedure_id",
            UUID(as_uuid=True),
            sa.ForeignKey("performed_procedures.id"),
            nullable=True,
        ),
        sa.Column("sifra", sa.String(20), nullable=False),
        sa.Column("naziv", sa.String(255), nullable=False),
        sa.Column("datum", sa.Date(), nullable=False),
        sa.Column("cijena_cents", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("predracun_stavke")
    op.drop_table("predracuni")
    op.drop_table("predracun_counters")
