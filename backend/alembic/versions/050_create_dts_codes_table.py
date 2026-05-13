"""add dts_codes table for local DTS procedure code search

DTS (Dijagnostičko-Terapijski Postupci) codes from CEZIH terminology.
Global table, not tenant-scoped. Same pattern as icd10_codes.

Revision ID: 050_dts_codes
Revises: 049_tenant_is_exam_tenant
"""

import sqlalchemy as sa

from alembic import op

revision = "050_dts_codes"
down_revision = "049_tenant_is_exam_tenant"


def upgrade() -> None:
    op.create_table(
        "dts_codes",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("display", sa.String(500), nullable=False),
        sa.Column(
            "system",
            sa.String(200),
            nullable=False,
            server_default="http://fhir.cezih.hr/specifikacije/CodeSystem/DTS",
        ),
        sa.Column("version", sa.String(20), nullable=False, server_default="0.1.0"),
        sa.Column("aktivan", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_dts_code"),
    )
    op.create_index("ix_dts_codes_code", "dts_codes", ["code"])
    op.execute("CREATE INDEX ix_dts_codes_search_trgm ON dts_codes USING gin (search_text gin_trgm_ops)")


def downgrade() -> None:
    op.drop_index("ix_dts_codes_search_trgm", table_name="dts_codes")
    op.drop_index("ix_dts_codes_code", table_name="dts_codes")
    op.drop_table("dts_codes")
