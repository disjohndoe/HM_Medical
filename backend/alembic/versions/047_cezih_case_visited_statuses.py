"""cezih_cases: add visited_clinical_statuses JSONB column

Append-only array tracking which clinical statuses a case has already
visited (remission, relapse, resolved). Used by the frontend to suppress
dead-end actions that CEZIH will reject with ERR_HEALTH_ISSUE_2004 after
a Remisija→Zatvori→Reopen cycle.

Revision ID: 047_cezih_case_visited_statuses
Revises: 046_add_djelatnost_columns
"""

import sqlalchemy as sa

from alembic import op

revision = "047_cezih_case_visited_statuses"
down_revision = "046_add_djelatnost_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cezih_cases",
        sa.Column(
            "visited_clinical_statuses",
            sa.JSON(),
            nullable=True,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("cezih_cases", "visited_clinical_statuses")
