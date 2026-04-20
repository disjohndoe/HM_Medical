"""CEZIH registries dispatcher — health checks, terminology, subject registry."""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.cezih import service as real_service
from app.services.cezih.dispatchers.common import _raise_cezih_error, _require_audit_params, _write_audit
from app.services.cezih.exceptions import CezihError

logger = logging.getLogger(__name__)


async def cezih_status(tenant_id=None, *, http_client=None) -> dict:
    """Check CEZIH connectivity status.

    Server cannot reach CEZIH directly (no VPN),
    so derive connectivity from agent + VPN status.
    """
    from app.services.agent_connection_manager import agent_manager

    agent_connected = False
    vpn_connected = False
    last_heartbeat = None
    if tenant_id:
        agent_connected = agent_manager.is_connected(tenant_id)
        conn = agent_manager.get_any_connected(tenant_id)
        if conn:
            last_heartbeat = conn.last_heartbeat
            vpn_connected = conn.vpn_connected

    # CEZIH is reachable when the agent is connected with an active VPN tunnel
    connected = agent_connected and vpn_connected

    return {
        "connected": connected,
        "agent_connected": agent_connected,
        "last_heartbeat": last_heartbeat,
    }


async def drug_search(query: str) -> list[dict]:
    """Drug search — uses local HZZO drug DB."""
    from app.services.halmed_sync_service import search_drugs_db

    results = await search_drugs_db(query)
    return results


async def signing_health_check(*, http_client=None) -> dict:
    """Health check for CEZIH signing service."""
    if not http_client:
        return {"reachable": False, "reason": "HTTP client not available"}

    from app.services.cezih_signing import sign_health_check as real_health_check

    try:
        return await real_health_check(http_client)
    except Exception as e:
        logger.error("CEZIH signing health check failed: %s", e)
        return {"reachable": False, "reason": str(e)}


async def oid_generate(
    quantity: int = 1,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    """Generate OID(s) via CEZIH identifier registry (TC6)."""
    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.generate_oid(http_client, quantity)
    except CezihError as e:
        _raise_cezih_error(e)
    await _write_audit(db, tenant_id, user_id, action="oid_generate", details={"quantity": quantity})
    return result


async def code_system_query(
    system_name: str,
    query: str,
    count: int = 20,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> list[dict]:
    """Query a CEZIH code system (ITI-96 SVCM)."""
    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.query_code_system(http_client, system_name, query, count)
    except CezihError as e:
        _raise_cezih_error(e)
    await _write_audit(
        db, tenant_id, user_id, action="code_system_query",
        details={"system": system_name, "query": query},
    )
    return result


async def value_set_expand(
    url: str,
    filter_text: str | None = None,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> dict:
    """Expand a CEZIH value set (ITI-95 SVCM)."""
    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.expand_value_set(http_client, url, filter_text)
    except CezihError as e:
        _raise_cezih_error(e)
    await _write_audit(db, tenant_id, user_id, action="value_set_expand", details={"url": url})
    return result


async def organization_search(
    name: str,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> list[dict]:
    """Search organizations in CEZIH registry (ITI-90 mCSD)."""
    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.find_organizations(http_client, name)
    except CezihError as e:
        _raise_cezih_error(e)
    await _write_audit(db, tenant_id, user_id, action="organization_search", details={"name": name})
    return result


async def practitioner_search(
    name: str,
    *,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    http_client=None,
) -> list[dict]:
    """Search practitioners in CEZIH registry (ITI-90 mCSD)."""
    db, user_id, tenant_id = _require_audit_params(db, user_id, tenant_id)
    try:
        result = await real_service.find_practitioners(http_client, name)
    except CezihError as e:
        _raise_cezih_error(e)
    await _write_audit(db, tenant_id, user_id, action="practitioner_search", details={"name": name})
    return result


__all__ = [
    "cezih_status",
    "drug_search",
    "signing_health_check",
    "oid_generate",
    "code_system_query",
    "value_set_expand",
    "organization_search",
    "practitioner_search",
]
