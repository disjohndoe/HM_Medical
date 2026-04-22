"""expand_tenant_vrsta_for_all_specialties

Revision ID: a8c3e2f1d5b7
Revises: c1af963d4ec1
Create Date: 2026-03-24

Expand tenant vrsta from 3 dental-only options to 7 specialty-agnostic options.
Change default from 'stomatoloska' to 'privatna_ordinacija'.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a8c3e2f1d5b7"
down_revision: str | None = "c1af963d4ec1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop old constraint
    op.drop_constraint("ck_tenant_vrsta", "tenants", type_="check")

    # Add new expanded constraint
    op.create_check_constraint(
        "ck_tenant_vrsta",
        "tenants",
        "vrsta IN ('privatna_ordinacija', 'stomatoloska', 'poliklinika', "
        "'opca_medicina', 'dom_zdravlja', 'laboratorij', 'dijagnosticki_centar')",
    )

    # Update existing default value
    op.alter_column("tenants", "vrsta", server_default="privatna_ordinacija")

    # Migrate any existing rows that have the old default
    op.execute("UPDATE tenants SET vrsta = 'privatna_ordinacija' WHERE vrsta = 'stomatoloska'")


def downgrade() -> None:
    # Revert migrated rows back
    op.execute(
        "UPDATE tenants SET vrsta = 'stomatoloska' "
        "WHERE vrsta NOT IN ('stomatoloska', 'poliklinika', 'privatna_ordinacija')"
    )
    op.execute("UPDATE tenants SET vrsta = 'stomatoloska' WHERE vrsta = 'privatna_ordinacija'")

    # Restore old constraint
    op.drop_constraint("ck_tenant_vrsta", "tenants", type_="check")
    op.create_check_constraint(
        "ck_tenant_vrsta",
        "tenants",
        "vrsta IN ('stomatoloska', 'poliklinika', 'privatna_ordinacija')",
    )
    op.alter_column("tenants", "vrsta", server_default="stomatoloska")
