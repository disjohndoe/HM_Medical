"""Common dispatcher utilities — audit helpers and context management."""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def _write_audit(
    db: AsyncSession | None,
    tenant_id: UUID | None,
    user_id: UUID | None,
    action: str,
    resource_id: UUID | None = None,
    details: dict | None = None,
) -> None:
    """Write audit log for CEZIH operations (if DB session available)."""
    if not db or not tenant_id or not user_id:
        return
    from app.services.audit_service import write_audit

    await write_audit(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        resource_type="cezih",
        resource_id=resource_id,
        details=details,
    )


def _require_audit_params(
    db: AsyncSession | None, user_id: UUID | None, tenant_id: UUID | None,
) -> tuple[AsyncSession, UUID, UUID]:
    """Audit parameters are mandatory for traceability. Returns narrowed types.

    Also sets context so downstream helpers can:
    - route 8443 calls through the agent (tenant)
    - resolve per-user signing preference (user_id + db)
    """
    if not db or not user_id or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Interna greška: nedostaju parametri za revizijski zapis CEZIH operacije.",
        )
    from app.services.cezih.client import (
        current_db_session,
        current_tenant_id,
        current_user_id,
    )
    current_tenant_id.set(tenant_id)
    current_user_id.set(user_id)
    current_db_session.set(db)
    return db, user_id, tenant_id


__all__ = [
    "_write_audit",
    "_require_audit_params",
]
