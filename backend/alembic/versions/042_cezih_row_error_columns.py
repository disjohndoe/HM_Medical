"""add last_error_* columns to cezih_visits, cezih_cases, medical_records

Populated when a CEZIH call fails (by the dispatcher via a separate session
so the main txn rollback doesn't erase the error record), cleared on the next
successful CEZIH action on the same row. The frontend reads these columns
and renders the per-row error badge so the signal survives page refreshes.

Revision ID: 042_cezih_row_error_columns
Revises: 041_cezih_case_abatement
"""

import sqlalchemy as sa

from alembic import op

revision = "042_cezih_row_error_columns"
down_revision = "041_cezih_case_abatement"


def upgrade() -> None:
    for table in ("cezih_visits", "cezih_cases"):
        op.add_column(table, sa.Column("last_error_code", sa.String(128), nullable=True))
        op.add_column(table, sa.Column("last_error_display", sa.Text(), nullable=True))
        op.add_column(table, sa.Column("last_error_diagnostics", sa.Text(), nullable=True))
        op.add_column(table, sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("medical_records", sa.Column("cezih_last_error_code", sa.String(128), nullable=True))
    op.add_column("medical_records", sa.Column("cezih_last_error_display", sa.Text(), nullable=True))
    op.add_column("medical_records", sa.Column("cezih_last_error_diagnostics", sa.Text(), nullable=True))
    op.add_column("medical_records", sa.Column("cezih_last_error_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for col in ("last_error_at", "last_error_diagnostics", "last_error_display", "last_error_code"):
        op.drop_column("cezih_visits", col)
        op.drop_column("cezih_cases", col)
    for col in (
        "cezih_last_error_at",
        "cezih_last_error_diagnostics",
        "cezih_last_error_display",
        "cezih_last_error_code",
    ):
        op.drop_column("medical_records", col)
