"""clear stale trial_expires_at for non-trial tenants

Revision ID: 022
Revises: 021
Create Date: 2026-04-05
"""

from alembic import op

revision = "022_clear_stale_trial_expires"
down_revision = "021_add_predracun_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE tenants SET trial_expires_at = NULL WHERE plan_tier != 'trial' AND trial_expires_at IS NOT NULL")


def downgrade() -> None:
    pass
