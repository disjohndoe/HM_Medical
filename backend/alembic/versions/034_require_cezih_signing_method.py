"""require cezih_signing_method (no more NULL = system default)

Revision ID: 034_require_signing_method
Revises: 033_foreign_ids
Create Date: 2026-04-17

Removes the "Zadano (sustav)" option — every user must now explicitly be
'smartcard' or 'extsigner'. Existing NULLs are backfilled to 'extsigner'
(the working default), then the column is made NOT NULL and the CHECK
constraint tightened.
"""

import sqlalchemy as sa

from alembic import op

revision = "034_require_signing_method"
down_revision = "033_foreign_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE users SET cezih_signing_method = 'extsigner' WHERE cezih_signing_method IS NULL")
    op.alter_column(
        "users",
        "cezih_signing_method",
        existing_type=sa.String(length=20),
        nullable=False,
        server_default="extsigner",
    )
    op.drop_constraint("ck_user_cezih_signing_method", "users", type_="check")
    op.create_check_constraint(
        "ck_user_cezih_signing_method",
        "users",
        "cezih_signing_method IN ('smartcard', 'extsigner')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_user_cezih_signing_method", "users", type_="check")
    op.alter_column(
        "users",
        "cezih_signing_method",
        existing_type=sa.String(length=20),
        nullable=True,
        server_default=None,
    )
    op.create_check_constraint(
        "ck_user_cezih_signing_method",
        "users",
        "cezih_signing_method IS NULL OR cezih_signing_method IN ('smartcard', 'extsigner')",
    )
