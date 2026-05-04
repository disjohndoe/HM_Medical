"""tenants + users: add djelatnost_code and djelatnost_display

Per-clinic + per-user šifra djelatnosti zdravstvene zaštite for ITI-65 clinical
documents. Tenant value is the clinic default; user value (when set) overrides
for that doctor. All four columns nullable so existing rows keep working until
configured. Resolution at submit time (dispatchers/documents.py): user override
-> tenant default -> 422 fail-fast.

Revision ID: 046_add_djelatnost_columns
Revises: 045_terms_acceptance
"""

import sqlalchemy as sa

from alembic import op

revision = "046_add_djelatnost_columns"
down_revision = "045_terms_acceptance"


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("djelatnost_code", sa.String(length=8), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("djelatnost_display", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("djelatnost_code", sa.String(length=8), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("djelatnost_display", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "djelatnost_display")
    op.drop_column("users", "djelatnost_code")
    op.drop_column("tenants", "djelatnost_display")
    op.drop_column("tenants", "djelatnost_code")
