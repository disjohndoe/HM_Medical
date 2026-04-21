"""cezih_visits: add service_provider_code, practitioner_ids, diagnosis_case_ids

Local-first visit listing: CEZIH response becomes an upsert source, UI renders
the full local mirror. Adds the three fields we currently re-derive from the
CEZIH response so the DB alone can drive the table. Composite unique index on
(tenant_id, cezih_visit_id) makes the upsert safe.

Revision ID: 043_cezih_visits_local_first
Revises: 042_cezih_row_error_columns
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "043_cezih_visits_local_first"
down_revision = "042_cezih_row_error_columns"


def upgrade() -> None:
    op.add_column(
        "cezih_visits",
        sa.Column("service_provider_code", sa.String(30), nullable=True),
    )
    op.add_column(
        "cezih_visits",
        sa.Column(
            "practitioner_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "cezih_visits",
        sa.Column(
            "diagnosis_case_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_cezih_visits_tenant_cezih_visit_id",
        "cezih_visits",
        ["tenant_id", "cezih_visit_id"],
        unique=True,
        postgresql_where=sa.text("cezih_visit_id IS NOT NULL"),
    )
    # Backfill: all existing rows belong to the demo tenant and were created
    # by us, so they're "Naša" (our org = 999001464). Scoped to the known
    # tenant so a second tenant's rows (if any) stay NULL and get filled by
    # their own CEZIH calls later.
    op.execute(
        """
        UPDATE cezih_visits
        SET service_provider_code = '999001464'
        WHERE service_provider_code IS NULL
          AND tenant_id = '11111111-1111-1111-1111-111111111111'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_cezih_visits_tenant_cezih_visit_id", table_name="cezih_visits")
    op.drop_column("cezih_visits", "diagnosis_case_ids")
    op.drop_column("cezih_visits", "practitioner_ids")
    op.drop_column("cezih_visits", "service_provider_code")
