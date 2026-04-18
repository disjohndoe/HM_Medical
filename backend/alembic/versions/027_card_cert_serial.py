"""add card_certificate_serial column + normalize name uniqueness, add serial uniqueness

Revision ID: 027_card_cert_serial
Revises: 026_unique_card_binding
Create Date: 2026-04-15

"""
import sqlalchemy as sa

from alembic import op

revision = "027_card_cert_serial"
down_revision = "026_unique_card_binding"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("card_certificate_serial", sa.String(length=128), nullable=True),
    )

    op.execute("DROP INDEX IF EXISTS ux_users_card_holder_name_active")

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_users_card_holder_name_active
        ON users (UPPER(TRIM(card_holder_name)))
        WHERE card_holder_name IS NOT NULL AND is_active = true
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_users_card_cert_serial_active
        ON users (card_certificate_serial)
        WHERE card_certificate_serial IS NOT NULL AND is_active = true
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_users_card_cert_serial_active")
    op.execute("DROP INDEX IF EXISTS ux_users_card_holder_name_active")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_users_card_holder_name_active
        ON users (card_holder_name)
        WHERE card_holder_name IS NOT NULL AND is_active = true
        """
    )
    op.drop_column("users", "card_certificate_serial")
