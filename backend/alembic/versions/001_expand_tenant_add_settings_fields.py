"""expand_tenant_add_settings_fields

Revision ID: 001_expand_tenant
Revises: cb18236e67df
Create Date: 2026-03-24 20:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "001_expand_tenant"
down_revision = "cb18236e67df"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns
    op.add_column("tenants", sa.Column("grad", sa.String(100), nullable=True))
    op.add_column("tenants", sa.Column("postanski_broj", sa.String(10), nullable=True))
    op.add_column("tenants", sa.Column("zupanija", sa.String(100), nullable=True))
    op.add_column("tenants", sa.Column("web", sa.String(255), nullable=True))
    op.add_column("tenants", sa.Column("sifra_ustanove", sa.String(20), nullable=True))
    op.add_column("tenants", sa.Column("oid", sa.String(50), nullable=True))

    # Update existing data: map old vrsta values to new ones
    op.execute(
        "UPDATE tenants SET vrsta = 'ordinacija' "
        "WHERE vrsta IN ('privatna_ordinacija', 'stomatoloska', "
        "'opca_medicina', 'laboratorij', 'dijagnosticki_centar')"
    )
    op.execute("UPDATE tenants SET cezih_status = 'nepovezano' WHERE cezih_status = 'none'")
    op.execute("UPDATE tenants SET cezih_status = 'u_pripremi' WHERE cezih_status = 'pending'")
    op.execute("UPDATE tenants SET cezih_status = 'certificirano' WHERE cezih_status = 'active'")
    op.execute("UPDATE tenants SET cezih_status = 'testirano' WHERE cezih_status = 'suspended'")
    op.execute("UPDATE tenants SET plan_tier = 'solo' WHERE plan_tier = 'basic'")
    op.execute("UPDATE tenants SET plan_tier = 'poliklinika' WHERE plan_tier = 'professional'")
    op.execute("UPDATE tenants SET plan_tier = 'poliklinika_plus' WHERE plan_tier = 'enterprise'")

    # Drop old check constraints and create new ones
    op.drop_constraint("ck_tenant_vrsta", "tenants", type_="check")
    op.create_check_constraint(
        "ck_tenant_vrsta",
        "tenants",
        "vrsta IN ('ordinacija', 'poliklinika', 'dom_zdravlja')",
    )

    op.drop_constraint("ck_tenant_cezih_status", "tenants", type_="check")
    op.create_check_constraint(
        "ck_tenant_cezih_status",
        "tenants",
        "cezih_status IN ('nepovezano', 'u_pripremi', 'testirano', 'certificirano')",
    )
    op.alter_column("tenants", "cezih_status", server_default="nepovezano")

    op.drop_constraint("ck_tenant_plan_tier", "tenants", type_="check")
    op.create_check_constraint(
        "ck_tenant_plan_tier",
        "tenants",
        "plan_tier IN ('trial', 'solo', 'poliklinika', 'poliklinika_plus')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_tenant_vrsta", "tenants", type_="check")
    op.create_check_constraint(
        "ck_tenant_vrsta",
        "tenants",
        "vrsta IN ('privatna_ordinacija', 'stomatoloska', 'poliklinika', "
        "'opca_medicina', 'dom_zdravlja', 'laboratorij', 'dijagnosticki_centar')",
    )

    op.drop_constraint("ck_tenant_cezih_status", "tenants", type_="check")
    op.create_check_constraint(
        "ck_tenant_cezih_status",
        "tenants",
        "cezih_status IN ('none', 'pending', 'active', 'suspended')",
    )

    op.drop_constraint("ck_tenant_plan_tier", "tenants", type_="check")
    op.create_check_constraint(
        "ck_tenant_plan_tier",
        "tenants",
        "plan_tier IN ('trial', 'basic', 'professional', 'enterprise')",
    )

    op.drop_column("tenants", "oid")
    op.drop_column("tenants", "sifra_ustanove")
    op.drop_column("tenants", "web")
    op.drop_column("tenants", "zupanija")
    op.drop_column("tenants", "postanski_broj")
    op.drop_column("tenants", "grad")
