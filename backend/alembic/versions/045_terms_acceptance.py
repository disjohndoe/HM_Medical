"""users: add terms_accepted_at and terms_version

Records consent to Terms of Service / Privacy Policy. Nullable so existing users
are flagged as not-yet-consented; login response prompts them with a blocking
modal until they accept.

Revision ID: 045_terms_acceptance
Revises: 044_add_cezih_last_replaced_at
"""

import sqlalchemy as sa

from alembic import op

revision = "045_terms_acceptance"
down_revision = "044_add_cezih_last_replaced_at"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("terms_version", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "terms_version")
    op.drop_column("users", "terms_accepted_at")
