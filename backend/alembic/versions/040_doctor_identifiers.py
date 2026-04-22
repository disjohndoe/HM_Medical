"""add doctor identifiers: mbo_lijecnika, tenant-scoped uniqueness, role gate

Revision ID: 040_doctor_identifiers
Revises: 039_cezih_ref_id
"""

import sqlalchemy as sa

from alembic import op

revision = "040_doctor_identifiers"
down_revision = "039_cezih_ref_id"


def upgrade() -> None:
    op.add_column("users", sa.Column("mbo_lijecnika", sa.String(9), nullable=True))

    op.execute(
        """
        CREATE UNIQUE INDEX ux_users_tenant_practitioner_id
        ON users (tenant_id, practitioner_id)
        WHERE practitioner_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX ux_users_tenant_mbo_lijecnika
        ON users (tenant_id, mbo_lijecnika)
        WHERE mbo_lijecnika IS NOT NULL
        """
    )

    op.create_check_constraint(
        "ck_user_role_can_hold_doctor_ids",
        "users",
        "role IN ('doctor','admin','nurse') OR (practitioner_id IS NULL AND mbo_lijecnika IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_user_role_can_hold_doctor_ids", "users", type_="check")
    op.execute("DROP INDEX ux_users_tenant_mbo_lijecnika")
    op.execute("DROP INDEX ux_users_tenant_practitioner_id")
    op.drop_column("users", "mbo_lijecnika")
