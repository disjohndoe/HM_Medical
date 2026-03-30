import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database import async_session
from app.models.tenant import Tenant
from app.services.agent_connection_manager import agent_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket):
    # Extract auth params from query string
    tenant_id_str = websocket.query_params.get("tenant_id")
    agent_secret = websocket.query_params.get("agent_secret")

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

    # Accept and register
    await agent_manager.connect(tenant_id, websocket)
    await websocket.send_json({"type": "connected", "message": "Agent spojen"})

    # Start ping loop
    ping_task = asyncio.create_task(_ping_loop(tenant_id))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")

            if msg_type == "pong":
                agent_manager.update_heartbeat(tenant_id)

            elif msg_type == "status":
                agent_manager.update_status(
                    tenant_id,
                    card_inserted=msg.get("card_inserted"),
                    vpn_connected=msg.get("vpn_connected"),
                    card_holder=msg.get("card_holder"),
                )

            elif msg_type in ("sign_response", "sign_error"):
                # Future: forward to waiting request
                logger.info("Received %s from agent for tenant %s", msg_type, tenant_id)

    except WebSocketDisconnect:
        logger.info("Agent WebSocket disconnected for tenant %s", tenant_id)
    except Exception:
        logger.exception("Agent WebSocket error for tenant %s", tenant_id)
    finally:
        ping_task.cancel()
        await agent_manager.disconnect(tenant_id)


async def _ping_loop(tenant_id):
    """Send ping every 30s to keep connection alive."""
    try:
        while True:
            await asyncio.sleep(30)
            sent = await agent_manager.send_to_agent(tenant_id, {"type": "ping"})
            if not sent:
                break
    except asyncio.CancelledError:
        pass
