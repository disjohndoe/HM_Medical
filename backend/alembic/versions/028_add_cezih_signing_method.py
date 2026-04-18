"""add cezih_signing_method per-user preference column

Revision ID: 028_cezih_signing_method
Revises: 027_card_cert_serial
Create Date: 2026-04-16

NULL = use system default (settings.CEZIH_SIGNING_METHOD env var).
'smartcard' = sign via local Tauri agent (NCrypt JWS).
'extsigner' = sign via Certilia remote signing (mobile push).
"""
import sqlalchemy as sa

from alembic import op

revision = "028_cezih_signing_method"
down_revision = "027_card_cert_serial"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("cezih_signing_method", sa.String(length=20), nullable=True),
    )
    op.create_check_constraint(
        "ck_user_cezih_signing_method",
        "users",
        "cezih_signing_method IS NULL OR cezih_signing_method IN ('smartcard', 'extsigner')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_user_cezih_signing_method", "users", type_="check")
    op.drop_column("users", "cezih_signing_method")
