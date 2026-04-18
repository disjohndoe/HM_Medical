"""add icd10_codes table for local ICD-10 search

Revision ID: 025_icd10_codes
Revises: a1b2c3d4e5f6
Create Date: 2026-04-13

"""
import sqlalchemy as sa

from alembic import op

revision = "025_icd10_codes"
down_revision = "a1b2c3d4e5f6"


def upgrade() -> None:
    op.create_table(
        "icd10_codes",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("display", sa.String(500), nullable=False),
        sa.Column(
            "system",
            sa.String(200),
            nullable=False,
            server_default="http://fhir.cezih.hr/specifikacije/CodeSystem/icd10-hr",
        ),
        sa.Column("aktivan", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_icd10_code"),
    )
    op.create_index("ix_icd10_codes_code", "icd10_codes", ["code"])
    op.execute(
        "CREATE INDEX ix_icd10_codes_search_trgm ON icd10_codes "
        "USING gin (search_text gin_trgm_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_icd10_codes_search_trgm", table_name="icd10_codes")
    op.drop_index("ix_icd10_codes_code", table_name="icd10_codes")
    op.drop_table("icd10_codes")
