import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select

from app.database import async_session
from app.models.tenant import Tenant
from app.models.user import User
from app.services import audit_service, auth_service
from app.config import settings
from app.services.agent_connection_manager import agent_manager

logger = logging.getLogger(__name__)

AUTH_TIMEOUT_SECONDS = 10

router = APIRouter()


@router.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket):
    # Auth via first message only (credentials NOT in URL/query params)
    await websocket.accept()
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT_SECONDS)
        msg = json.loads(raw)
    except (TimeoutError, json.JSONDecodeError):
        await websocket.close(code=4001, reason="Auth timeout or invalid message")
        return

    if msg.get("type") != "auth":
        await websocket.close(code=4001, reason="First message must be auth")
        return

    tenant_id_str = msg.get("tenant_id")
    agent_secret = msg.get("agent_secret")
    agent_id = msg.get("agent_id")

    if not tenant_id_str or not agent_secret:
        await websocket.close(code=4001, reason="Missing tenant_id or agent_secret")
        return

    try:
        tenant_id = UUID(tenant_id_str)
    except ValueError:
        await websocket.close(code=4001, reason="Invalid tenant_id format")
        return

    # Verify secret against DB
    async with async_session() as db:
        tenant = await db.get(Tenant, tenant_id)
        if not tenant or tenant.agent_secret != agent_secret:
            await websocket.close(code=4003, reason="Invalid credentials")
            return

    # Register connection
    conn = await agent_manager.register(tenant_id, websocket, agent_id)
    agent_id = conn.agent_id
    # Include CEZIH warmup URL so agent can establish mTLS session on connect.
    # Target encounter service (8443) specifically — same service used by TC12-14 POST.
    # Triggers single PIN prompt on connect instead of on first user action.
    warmup_url = ""
    if settings.CEZIH_FHIR_BASE_URL:
        base = settings.CEZIH_FHIR_BASE_URL.rstrip("/")
        warmup_url = f"{base}/services-router/gateway/encounter-services/api/v1/Encounter?_count=1"
    await websocket.send_json({
        "type": "connected",
        "message": "Agent spojen",
        "agent_id": agent_id,
        "cezih_warmup_url": warmup_url,
    })

    # Start ping loop
    ping_task = asyncio.create_task(_ping_loop(tenant_id, agent_id))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")

            if msg_type == "pong":
                agent_manager.update_heartbeat(tenant_id, agent_id)

            elif msg_type == "status":
                # Capture previous card state BEFORE update
                current_conn = agent_manager.get_by_agent(tenant_id, agent_id)
                was_inserted = current_conn.card_inserted if current_conn else False
                previous_card_holder = current_conn.card_holder if current_conn else None

                agent_manager.update_status(
                    tenant_id,
                    agent_id,
                    card_inserted=msg.get("card_inserted"),
                    vpn_connected=msg.get("vpn_connected"),
                    card_holder=msg.get("card_holder"),
                    readers=msg.get("readers"),
                )

                # Card removal detection: revoke only the affected doctor's sessions
                now_inserted = msg.get("card_inserted", was_inserted)
                if was_inserted and not now_inserted:
                    await _handle_card_removal(tenant_id, agent_id, previous_card_holder)

            elif msg_type == "http_proxy_response":
                req_id = msg.get("request_id", "")
                agent_manager.resolve_proxy_response(req_id, msg)

            elif msg_type in ("sign_response", "sign_error"):
                # Future: forward to waiting request
                logger.info("Received %s from agent %s for tenant %s", msg_type, agent_id[:8], tenant_id)

    except WebSocketDisconnect:
        logger.info("Agent %s disconnected for tenant %s", agent_id[:8], tenant_id)
    except Exception:
        logger.exception("Agent %s WebSocket error for tenant %s", agent_id[:8], tenant_id)
    finally:
        ping_task.cancel()
        # Revoke card-required sessions if card was inserted when agent disconnected
        current_conn = agent_manager.get_by_agent(tenant_id, agent_id)
        if current_conn and current_conn.card_inserted:
            await _handle_card_removal(tenant_id, agent_id, current_conn.card_holder)
        await agent_manager.disconnect(tenant_id, agent_id)


async def _ping_loop(tenant_id: UUID, agent_id: str):
    """Send ping every 30s to keep connection alive."""
    try:
        while True:
            await asyncio.sleep(30)
            sent = await agent_manager.send_to_agent(tenant_id, agent_id, {"type": "ping"})
            if not sent:
                break
    except asyncio.CancelledError:
        pass


async def _handle_card_removal(tenant_id: UUID, agent_id: str, card_holder: str | None) -> None:
    """Revoke sessions only for the doctor whose card was removed from this agent."""
    if not card_holder:
        logger.warning("Card removal on agent %s for tenant %s — no card_holder to match", agent_id[:8], tenant_id)
        return

    logger.warning(
        "Card removal detected on agent %s for tenant %s (holder: %s)",
        agent_id[:8], tenant_id, card_holder,
    )

    async with async_session() as db:
        async with db.begin():
            # Find the specific user whose card was removed
            result = await db.execute(
                select(User).where(
                    User.tenant_id == tenant_id,
                    User.card_required.is_(True),
                    User.is_active.is_(True),
                    func.upper(func.trim(User.card_holder_name)) == card_holder.strip().upper(),
                )
            )
            user = result.scalars().first()

            if user:
                count = await auth_service.revoke_user_sessions(db, tenant_id, user.id)
                if count > 0:
                    logger.info(
                        "Revoked %d session(s) for user %s (card removal from agent %s)",
                        count, user.email, agent_id[:8],
                    )
                    await audit_service.write_audit(
                        db,
                        tenant_id=tenant_id,
                        user_id=user.id,
                        action="card_removal_session_revoked",
                        resource_type="session",
                        details={"sessions_revoked": count, "agent_id": agent_id},
                    )
