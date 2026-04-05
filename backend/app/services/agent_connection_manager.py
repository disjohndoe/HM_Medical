import logging
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class AgentConnection:
    tenant_id: UUID
    agent_id: str
    websocket: WebSocket
    connected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_heartbeat: datetime | None = None
    card_inserted: bool = False
    vpn_connected: bool = False
    card_holder: str | None = None
    card_removed_at: datetime | None = None


class AgentConnectionManager:
    """Manages multiple agent connections per tenant.

    Data structure: tenant_id -> {agent_id -> AgentConnection}
    """

    def __init__(self) -> None:
        self._connections: dict[UUID, dict[str, AgentConnection]] = {}

    async def connect(
        self, tenant_id: UUID, websocket: WebSocket, agent_id: str | None = None
    ) -> AgentConnection:
        if agent_id is None:
            agent_id = str(_uuid.uuid4())

        tenant_agents = self._connections.setdefault(tenant_id, {})

        # Replace existing connection for same agent_id (reconnect)
        if agent_id in tenant_agents:
            old = tenant_agents.pop(agent_id)
            logger.info("Replacing agent %s for tenant %s", agent_id[:8], tenant_id)
            try:
                await old.websocket.close()
            except Exception:
                pass

        await websocket.accept()
        conn = AgentConnection(tenant_id=tenant_id, agent_id=agent_id, websocket=websocket)
        tenant_agents[agent_id] = conn
        logger.info(
            "Agent %s connected for tenant %s (total: %d)",
            agent_id[:8], tenant_id, len(tenant_agents),
        )
        return conn

    async def disconnect(self, tenant_id: UUID, agent_id: str) -> None:
        tenant_agents = self._connections.get(tenant_id)
        if not tenant_agents:
            return
        conn = tenant_agents.pop(agent_id, None)
        if conn:
            logger.info("Agent %s disconnected for tenant %s", agent_id[:8], tenant_id)
            try:
                await conn.websocket.close()
            except Exception:
                pass
        # Clean up empty tenant entry
        if not tenant_agents:
            self._connections.pop(tenant_id, None)

    def get_by_agent(self, tenant_id: UUID, agent_id: str) -> AgentConnection | None:
        tenant_agents = self._connections.get(tenant_id)
        if not tenant_agents:
            return None
        return tenant_agents.get(agent_id)

    def get_any_connected(self, tenant_id: UUID) -> AgentConnection | None:
        tenant_agents = self._connections.get(tenant_id)
        if not tenant_agents:
            return None
        return next(iter(tenant_agents.values()), None)

    def get_all(self, tenant_id: UUID) -> list[AgentConnection]:
        tenant_agents = self._connections.get(tenant_id)
        if not tenant_agents:
            return []
        return list(tenant_agents.values())

    def find_by_card_holder(
        self, tenant_id: UUID, card_holder_name: str
    ) -> AgentConnection | None:
        tenant_agents = self._connections.get(tenant_id)
        if not tenant_agents:
            return None
        target = card_holder_name.strip().upper()
        for conn in tenant_agents.values():
            if conn.card_inserted and conn.card_holder and conn.card_holder.strip().upper() == target:
                return conn
        return None

    def is_connected(self, tenant_id: UUID) -> bool:
        tenant_agents = self._connections.get(tenant_id)
        return bool(tenant_agents)

    def count(self, tenant_id: UUID) -> int:
        tenant_agents = self._connections.get(tenant_id)
        return len(tenant_agents) if tenant_agents else 0

    def update_heartbeat(self, tenant_id: UUID, agent_id: str) -> None:
        conn = self.get_by_agent(tenant_id, agent_id)
        if conn:
            conn.last_heartbeat = datetime.now(UTC)

    def update_status(
        self,
        tenant_id: UUID,
        agent_id: str,
        *,
        card_inserted: bool | None = None,
        vpn_connected: bool | None = None,
        card_holder: str | None = None,
    ) -> None:
        conn = self.get_by_agent(tenant_id, agent_id)
        if not conn:
            return
        if card_inserted is not None:
            if conn.card_inserted and not card_inserted:
                conn.card_removed_at = datetime.now(UTC)
            elif card_inserted:
                conn.card_removed_at = None
            conn.card_inserted = card_inserted
        if vpn_connected is not None:
            conn.vpn_connected = vpn_connected
        if card_holder is not None:
            conn.card_holder = card_holder

    async def send_to_agent(self, tenant_id: UUID, agent_id: str, message: dict) -> bool:
        conn = self.get_by_agent(tenant_id, agent_id)
        if not conn:
            return False
        try:
            await conn.websocket.send_json(message)
            return True
        except Exception:
            logger.warning("Failed to send to agent %s for tenant %s", agent_id[:8], tenant_id)
            await self.disconnect(tenant_id, agent_id)
            return False


agent_manager = AgentConnectionManager()
