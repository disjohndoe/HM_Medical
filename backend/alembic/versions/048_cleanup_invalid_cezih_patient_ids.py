"""null-out non-numeric cezih_patient_id values

HZZO Provjera Spremnosti rejected 2026-05-11 because a CUID-shaped value
(e.g. "cmj70ejct00se5c85hg2eax6p") was being sent as
jedinstveni-identifikator-pacijenta. CEZIH-assigned JIDs are always
numeric. Any non-numeric value in this column came from a pre-fix code
path and must be cleared so the next CEZIH action either falls through
to another identifier (OIB/MBO/EHIC/putovnica) or prompts the doctor to
re-register the foreigner via TC11 PMIR.

Idempotent: rows already cleared are no-ops. Downgrade is intentionally
empty — we never want to re-inject bad values.

Revision ID: 048_cleanup_invalid_cezih_patient_ids
Revises: 047_cezih_case_visited_statuses
"""

from alembic import op

revision = "048_cleanup_invalid_cezih_patient_ids"
down_revision = "047_cezih_case_visited_statuses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres regex: ~ is case-sensitive match, !~ is negation.
    # Match anything that is not pure digits (covers empty string too, though
    # IS NOT NULL already filters those out for us).
    op.execute(
        """
        UPDATE patients
        SET cezih_patient_id = NULL
        WHERE cezih_patient_id IS NOT NULL
          AND cezih_patient_id !~ '^[0-9]+$'
        """
    )


def downgrade() -> None:
    # Intentionally empty — values cleared here were invalid and should
    # not be restored. Re-run PMIR (TC11) to obtain a valid JID.
    pass
