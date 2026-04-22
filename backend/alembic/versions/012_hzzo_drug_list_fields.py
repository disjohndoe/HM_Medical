"""hzzo drug list fields — widen atk, add hzzo_lista, r_rs, nacin, doplata

Revision ID: 012_hzzo_drugs
Revises: 011_drug_list
Create Date: 2026-03-31

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "012_hzzo_drugs"
down_revision: str | None = "011_drug_list"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Widen atk column
    op.alter_column("drug_list", "atk", type_=sa.String(20), nullable=False)
    # Widen oblik to fit HZZO combined form/strength/packaging
    op.alter_column("drug_list", "oblik", type_=sa.String(500), nullable=False, server_default="")
    # Widen hzzo_sifra
    op.alter_column("drug_list", "hzzo_sifra", type_=sa.String(20), nullable=False, server_default="")
    # Add new HZZO columns
    op.add_column("drug_list", sa.Column("hzzo_lista", sa.String(3), nullable=False, server_default=""))
    op.add_column("drug_list", sa.Column("r_rs", sa.String(3), nullable=False, server_default=""))
    op.add_column("drug_list", sa.Column("nacin_primjene", sa.String(5), nullable=False, server_default=""))
    op.add_column("drug_list", sa.Column("doplata", sa.String(20), nullable=False, server_default=""))
    # Add index on hzzo_lista for filtering
    op.create_index("ix_drug_list_hzzo_lista", "drug_list", ["hzzo_lista"])
    # Unique constraint for upsert dedup — same drug can appear in both lists
    op.create_unique_constraint("uq_drug_list_atk_naziv_oblik", "drug_list", ["atk", "naziv", "oblik"])


def downgrade() -> None:
    op.drop_constraint("uq_drug_list_atk_naziv_oblik", "drug_list", type_="unique")
    op.drop_index("ix_drug_list_hzzo_lista", table_name="drug_list")
    op.drop_column("drug_list", "doplata")
    op.drop_column("drug_list", "nacin_primjene")
    op.drop_column("drug_list", "r_rs")
    op.drop_column("drug_list", "hzzo_lista")
    op.alter_column("drug_list", "hzzo_sifra", type_=sa.String(11), nullable=False, server_default="")
    op.alter_column("drug_list", "oblik", type_=sa.String(255), nullable=False, server_default="")
    op.alter_column("drug_list", "atk", type_=sa.String(7), nullable=False)
