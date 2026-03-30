import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class AgentConnection:
    tenant_id: UUID
    websocket: WebSocket
    connected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_heartbeat: datetime | None = None
    card_inserted: bool = False
    vpn_connected: bool = False
    card_holder: str | None = None


class AgentConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[UUID, AgentConnection] = {}

    async def connect(self, tenant_id: UUID, websocket: WebSocket) -> AgentConnection:
        # Replace existing connection for this tenant
        if tenant_id in self._connections:
            old = self._connections.pop(tenant_id)
            logger.info("Replacing existing agent connection for tenant %s", tenant_id)
            try:
                await old.websocket.close()
            except Exception:
                pass

        await websocket.accept()
        conn = AgentConnection(tenant_id=tenant_id, websocket=websocket)
        self._connections[tenant_id] = conn
        logger.info("Agent connected for tenant %s", tenant_id)
        return conn

    async def disconnect(self, tenant_id: UUID) -> None:
        conn = self._connections.pop(tenant_id, None)
        if conn:
            logger.info("Agent disconnected for tenant %s", tenant_id)
            try:
                await conn.websocket.close()
            except Exception:
                pass

    def get(self, tenant_id: UUID) -> AgentConnection | None:
        return self._connections.get(tenant_id)

    def is_connected(self, tenant_id: UUID) -> bool:
        return tenant_id in self._connections

    def update_heartbeat(self, tenant_id: UUID) -> None:
        conn = self._connections.get(tenant_id)
        if conn:
            conn.last_heartbeat = datetime.now(UTC)

    def update_status(
        self,
        tenant_id: UUID,
        *,
        card_inserted: bool | None = None,
        vpn_connected: bool | None = None,
        card_holder: str | None = None,
    ) -> None:
        conn = self._connections.get(tenant_id)
        if not conn:
            return
        if card_inserted is not None:
            conn.card_inserted = card_inserted
        if vpn_connected is not None:
            conn.vpn_connected = vpn_connected
        if card_holder is not None:
            conn.card_holder = card_holder

    async def send_to_agent(self, tenant_id: UUID, message: dict) -> bool:
        conn = self._connections.get(tenant_id)
        if not conn:
            return False
        try:
            await conn.websocket.send_json(message)
            return True
        except Exception:
            logger.warning("Failed to send message to agent for tenant %s", tenant_id)
            await self.disconnect(tenant_id)
            return False


agent_manager = AgentConnectionManager()
