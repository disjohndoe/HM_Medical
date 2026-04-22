"""enforce globally unique card_holder_name per active user

Revision ID: 026_unique_card_binding
Revises: 025_icd10_codes
Create Date: 2026-04-15

"""

from alembic import op

revision = "026_unique_card_binding"
down_revision = "025_icd10_codes"


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_users_card_holder_name_active
        ON users (card_holder_name)
        WHERE card_holder_name IS NOT NULL AND is_active = true
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_users_card_holder_name_active")
