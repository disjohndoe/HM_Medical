"""add tenants.is_exam_tenant flag

For HZZO certification we need the test ordinacija (HM DIGITAL,
sifra_ustanove = '999001464') to bypass the djelatnost-based UI filter
so all three doc types (011/012/013) can be demoed on one account. Real
tenants stay locked to options their šifra djelatnosti zdravstvene
zaštite allows. Flag defaults to false; backfilled true for our test
institution.

Revision ID: 049_tenant_is_exam_tenant
Revises: 048_null_bad_cezih_patient_ids
"""

import sqlalchemy as sa

from alembic import op

revision = "049_tenant_is_exam_tenant"
down_revision = "048_null_bad_cezih_patient_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "is_exam_tenant",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.execute(
        """
        UPDATE tenants
        SET is_exam_tenant = true
        WHERE sifra_ustanove = '999001464'
        """
    )


def downgrade() -> None:
    op.drop_column("tenants", "is_exam_tenant")
