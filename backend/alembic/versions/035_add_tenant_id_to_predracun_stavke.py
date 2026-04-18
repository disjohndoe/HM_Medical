"""Add tenant_id + timestamps to predracun_stavke

Revision ID: 035_predracun_stavke_tenant
Revises: 034_require_signing_method
Create Date: 2026-04-18

PredracunStavka previously inherited from Base (no tenant_id).
Now uses BaseTenantModel for proper tenant isolation.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "035_predracun_stavke_tenant"
down_revision = "034_require_signing_method"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add nullable tenant_id column
    op.add_column(
        "predracun_stavke",
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=True),
    )

    # Backfill from parent predracuni
    op.execute(
        """
        UPDATE predracun_stavke ps
        SET tenant_id = p.tenant_id
        FROM predracuni p
        WHERE ps.predracun_id = p.id
        """
    )

    # Make NOT NULL
    op.alter_column("predracun_stavke", "tenant_id", nullable=False)

    # Add FK + index
    op.create_foreign_key(
        "fk_predracun_stavke_tenant",
        "predracun_stavke",
        "tenants",
        ["tenant_id"],
        ["id"],
    )
    op.create_index(
        "ix_predracun_stavke_tenant",
        "predracun_stavke",
        ["tenant_id"],
    )

    # Add timestamps (from TimestampMixin)
    op.add_column(
        "predracun_stavke",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.add_column(
        "predracun_stavke",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("predracun_stavke", "updated_at")
    op.drop_column("predracun_stavke", "created_at")
    op.drop_index("ix_predracun_stavke_tenant", table_name="predracun_stavke")
    op.drop_constraint("fk_predracun_stavke_tenant", "predracun_stavke", type_="foreignkey")
    op.drop_column("predracun_stavke", "tenant_id")
