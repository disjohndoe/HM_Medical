"""drop tenants.is_exam_tenant flag

HZZO provjera spremnosti passed (zapisnik signed 2026-05-28). The exam-tenant
bypass (all three CEZIH doc types on one account) is no longer needed. Every
tenant is now filtered strictly by its šifra djelatnosti zdravstvene zaštite.

Revision ID: 054_drop_is_exam_tenant
Revises: 053_cezih_case_registered
"""

import sqlalchemy as sa

from alembic import op

revision = "054_drop_is_exam_tenant"
down_revision = "053_cezih_case_registered"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("tenants", "is_exam_tenant")


def downgrade() -> None:
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
