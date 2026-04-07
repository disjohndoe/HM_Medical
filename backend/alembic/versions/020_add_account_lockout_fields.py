"""add account lockout fields to users

Revision ID: 020
Revises: 019
Create Date: 2026-04-05
"""
import sqlalchemy as sa

from alembic import op

revision = "020_add_account_lockout_fields"
down_revision = "019_add_cezih_signature_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("failed_login_attempts", sa.Integer(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")
