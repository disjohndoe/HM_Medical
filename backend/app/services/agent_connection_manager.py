import asyncio
import logging
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Pending HTTP proxy / sign requests: request_id -> (tenant_id, future).
# Tenant is tracked so we can fail-fast pending requests when a specific
# tenant's agent disconnects, rather than making callers wait the full timeout.
_pending_proxy: dict[str, tuple[UUID, asyncio.Future]] = {}


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
    card_serial: str | None = None
    card_subject_oib: str | None = None
    card_removed_at: datetime | None = None
    readers: list[dict] = field(default_factory=list)


class AgentConnectionManager:
    """Manages multiple agent connections per tenant.

    Data structure: tenant_id -> {agent_id -> AgentConnection}
    """

    def __init__(self) -> None:
        self._connections: dict[UUID, dict[str, AgentConnection]] = {}

    async def register(self, tenant_id: UUID, websocket: WebSocket, agent_id: str | None = None) -> AgentConnection:
        """Register an already-accepted WebSocket connection (message-based auth)."""
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

        conn = AgentConnection(tenant_id=tenant_id, agent_id=agent_id, websocket=websocket)
        tenant_agents[agent_id] = conn
        logger.info(
            "Agent %s connected for tenant %s (total: %d)",
            agent_id[:8],
            tenant_id,
            len(tenant_agents),
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
        # Fail any pending sign/proxy requests for this tenant so callers
        # (visit creation, document send, etc.) error out immediately instead
        # of waiting the full 300s signing timeout. Without this, a dropped
        # WS during PIN entry leaves the HTTP handler stuck. In multi-agent
        # tenants this is coarse (we don't track which agent each request was
        # sent to) but tenants run one agent per machine today.
        _fail_pending_for_tenant(tenant_id)

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

    def find_by_card_holder(self, tenant_id: UUID, card_holder_name: str) -> AgentConnection | None:
        tenant_agents = self._connections.get(tenant_id)
        if not tenant_agents:
            return None
        if not card_holder_name:
            return None
        target = card_holder_name.strip().upper()
        for conn in tenant_agents.values():
            # Check top-level field (backward compat with old agents)
            if conn.card_inserted and conn.card_holder and conn.card_holder.strip().upper() == target:
                return conn
            # Check readers array (multi-reader support)
            for reader in conn.readers:
                if reader.get("card_inserted") and (reader.get("card_holder") or "").strip().upper() == target:
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
        card_serial: str | None = None,
        card_subject_oib: str | None = None,
        readers: list[dict] | None = None,
    ) -> None:
        conn = self.get_by_agent(tenant_id, agent_id)
        if not conn:
            return
        if card_inserted is not None:
            if conn.card_inserted and not card_inserted:
                conn.card_removed_at = datetime.now(UTC)
                conn.card_serial = None
                conn.card_subject_oib = None
            elif card_inserted:
                conn.card_removed_at = None
            conn.card_inserted = card_inserted
        if vpn_connected is not None:
            conn.vpn_connected = vpn_connected
        if card_holder is not None:
            conn.card_holder = card_holder
        if card_serial is not None:
            conn.card_serial = card_serial
        if card_subject_oib is not None:
            conn.card_subject_oib = card_subject_oib
        if readers is not None:
            conn.readers = readers

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

    async def proxy_http_request(
        self,
        tenant_id: UUID,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: str | None = None,
        timeout: float = 300.0,
        card_holder_name: str | None = None,
    ) -> dict:
        """Send an HTTP request through a connected agent and wait for the response.

        The agent makes the actual HTTP call with native TLS (smart card mTLS).
        If card_holder_name is specified, prefers the agent whose inserted card
        matches that holder (for multi-doctor tenants with separate machines).
        Returns the parsed response dict or raises an exception.
        """
        conn = None
        if card_holder_name:
            conn = self.find_by_card_holder(tenant_id, card_holder_name)
        if not conn:
            conn = self.get_any_connected(tenant_id)
        if not conn:
            raise RuntimeError("No agent connected for this tenant")

        request_id = str(_uuid.uuid4())
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        _pending_proxy[request_id] = (tenant_id, future)

        message = {
            "type": "http_proxy_request",
            "request_id": request_id,
            "method": method,
            "url": url,
            "headers": headers,
            "body": body,
        }

        try:
            await conn.websocket.send_json(message)
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except TimeoutError:
            raise RuntimeError(f"Agent HTTP proxy timed out after {timeout}s")
        finally:
            _pending_proxy.pop(request_id, None)

    async def sign_jws(
        self,
        tenant_id: UUID,
        *,
        data_base64: str,
        timeout: float = 300.0,
    ) -> dict:
        """Send data to the agent for JWS signing (NCryptSignHash).

        The agent builds the full x5c cert chain from the Windows cert store and
        signs using NCryptSignHash. Returns jws_base64 + kid + algorithm.
        """
        conn = self.get_any_connected(tenant_id)
        if not conn:
            raise RuntimeError("No agent connected for this tenant")

        request_id = str(_uuid.uuid4())
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        _pending_proxy[request_id] = (tenant_id, future)

        message: dict = {
            "type": "sign_jws",
            "request_id": request_id,
            "data": data_base64,
        }

        try:
            await conn.websocket.send_json(message)
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except TimeoutError:
            raise RuntimeError(f"Agent JWS signing timed out after {timeout}s")
        finally:
            _pending_proxy.pop(request_id, None)

    async def get_cert_info(
        self,
        tenant_id: UUID,
        *,
        timeout: float = 15.0,
    ) -> dict:
        """Get certificate info (kid, algorithm) from the agent's smart card.

        No signing performed — just reads cert thumbprint and determines algorithm.
        """
        conn = self.get_any_connected(tenant_id)
        if not conn:
            raise RuntimeError("No agent connected for this tenant")

        request_id = str(_uuid.uuid4())
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        _pending_proxy[request_id] = (tenant_id, future)

        message = {
            "type": "get_cert_info",
            "request_id": request_id,
        }

        try:
            await conn.websocket.send_json(message)
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except TimeoutError:
            raise RuntimeError(f"Agent get_cert_info timed out after {timeout}s")
        finally:
            _pending_proxy.pop(request_id, None)

    async def sign_raw(
        self,
        tenant_id: UUID,
        *,
        data_base64: str,
        algorithm: str = "RS256",
        timeout: float = 300.0,
    ) -> dict:
        """Send raw bytes to agent for signing.

        The agent hashes the data and signs via NCryptSignHash.
        Returns dict with 'signature' (base64), 'kid', 'algorithm',
        or 'error' string on failure.
        """
        conn = self.get_any_connected(tenant_id)
        if not conn:
            raise RuntimeError("No agent connected for this tenant")

        request_id = str(_uuid.uuid4())
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        _pending_proxy[request_id] = (tenant_id, future)

        message = {
            "type": "sign_raw",
            "request_id": request_id,
            "data": data_base64,
            "algorithm": algorithm,
        }

        try:
            await conn.websocket.send_json(message)
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except TimeoutError:
            raise RuntimeError(f"Agent sign_raw timed out after {timeout}s")
        finally:
            _pending_proxy.pop(request_id, None)

    async def sign_data(
        self,
        tenant_id: UUID,
        *,
        data_base64: str,
        timeout: float = 300.0,
    ) -> dict:
        """Send data to the agent for signing with the smart card.

        The agent signs using Windows CryptoAPI + AKD signing certificate.
        Returns dict with 'signature' (base64) and 'kid' (cert thumbprint),
        or 'error' string on failure.
        """
        conn = self.get_any_connected(tenant_id)
        if not conn:
            raise RuntimeError("No agent connected for this tenant")

        request_id = str(_uuid.uuid4())
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        _pending_proxy[request_id] = (tenant_id, future)  # reuse same pending dict

        message = {
            "type": "sign_request",
            "request_id": request_id,
            "data": data_base64,
        }

        try:
            await conn.websocket.send_json(message)
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except TimeoutError:
            raise RuntimeError(f"Agent signing timed out after {timeout}s")
        finally:
            _pending_proxy.pop(request_id, None)

    @staticmethod
    def resolve_proxy_response(request_id: str, response: dict) -> None:
        """Called when agent sends http_proxy_response or sign_response — resolves the waiting future."""
        entry = _pending_proxy.get(request_id)
        if entry is None:
            logger.warning("No pending proxy request for id %s", request_id[:8])
            return
        _tenant_id, future = entry
        if not future.done():
            future.set_result(response)
        else:
            logger.warning("Proxy response for already-resolved id %s", request_id[:8])


def _fail_pending_for_tenant(tenant_id: UUID) -> None:
    """Reject futures tied to this tenant so waiting callers unblock fast."""
    to_fail = [rid for rid, (t, fut) in _pending_proxy.items() if t == tenant_id and not fut.done()]
    for rid in to_fail:
        entry = _pending_proxy.get(rid)
        if entry is None:
            continue
        _t, fut = entry
        if not fut.done():
            fut.set_exception(RuntimeError("Agent disconnected before responding"))


agent_manager = AgentConnectionManager()
