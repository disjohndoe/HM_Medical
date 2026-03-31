"""add record_types table — tenant-configurable medical record types

Revision ID: 018_add_record_types_table
Revises: 017_drop_cezih_visits
Create Date: 2026-04-01

Each tenant gets 9 seeded system types (3 CEZIH mandatory + 6 general).
Admins can add custom types per tenant. CEZIH mandatory types are locked.
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "018_add_record_types_table"
down_revision = "017_drop_cezih_visits"
branch_labels = None
depends_on = None

SYSTEM_TYPES = [
    # slug, label, color, is_cezih_mandatory, is_cezih_eligible, sort_order
    ("ambulantno_izvjesce", "Ambulantno izvješće", "bg-emerald-100 text-emerald-800", True, True, 0),
    ("specijalisticki_nalaz", "Specijalistički nalaz", "bg-indigo-100 text-indigo-800", True, True, 1),
    ("otpusno_pismo", "Otpusno pismo", "bg-rose-100 text-rose-800", True, True, 2),
    ("nalaz", "Nalaz", "bg-blue-100 text-blue-800", False, True, 3),
    ("epikriza", "Epikriza", "bg-amber-100 text-amber-800", False, True, 4),
    ("dijagnoza", "Dijagnoza", "bg-red-100 text-red-800", False, False, 5),
    ("misljenje", "Mišljenje", "bg-purple-100 text-purple-800", False, False, 6),
    ("preporuka", "Preporuka", "bg-green-100 text-green-800", False, False, 7),
    ("anamneza", "Anamneza", "bg-cyan-100 text-cyan-800", False, False, 8),
]


def upgrade() -> None:
    op.create_table(
        "record_types",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("color", sa.String(length=50), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_cezih_mandatory", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_cezih_eligible", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_record_type_tenant_slug"),
    )
    op.create_index("ix_record_types_tenant_id", "record_types", ["tenant_id"])

    # Seed system record types for every existing tenant
    connection = op.get_bind()
    tenants = connection.execute(sa.text("SELECT id FROM tenants")).fetchall()

    for tenant in tenants:
        for slug, label, color, is_cezih_mandatory, is_cezih_eligible, sort_order in SYSTEM_TYPES:
            connection.execute(
                sa.text(
                    "INSERT INTO record_types "
                    "(id, tenant_id, slug, label, color, is_system, is_cezih_mandatory, is_cezih_eligible, is_active, sort_order) "
                    "VALUES (:id, :tenant_id, :slug, :label, :color, true, :is_cezih_mandatory, :is_cezih_eligible, true, :sort_order)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": str(tenant[0]),
                    "slug": slug,
                    "label": label,
                    "color": color,
                    "is_cezih_mandatory": is_cezih_mandatory,
                    "is_cezih_eligible": is_cezih_eligible,
                    "sort_order": sort_order,
                },
            )


def downgrade() -> None:
    op.drop_index("ix_record_types_tenant_id", table_name="record_types")
    op.drop_table("record_types")
