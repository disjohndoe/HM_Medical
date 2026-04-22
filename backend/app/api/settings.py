import secrets
import time
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import limiter
from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.tenant import TenantRead, TenantUpdate
from app.services.agent_connection_manager import agent_manager
from app.services.card_verification import get_card_status
from app.services.cezih import dispatcher as cezih_dispatcher

router = APIRouter(prefix="/settings", tags=["settings"])


class CezihStatusResponse(BaseModel):
    status: str
    sifra_ustanove: str | None
    oid: str | None
    agent_connected: bool
    agents_count: int = 0
    last_heartbeat: datetime | None


@router.get("/clinic", response_model=TenantRead)
async def get_clinic_settings(
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    tenant = await db.get(Tenant, current_user.tenant_id)
    return tenant


@router.patch("/clinic", response_model=TenantRead)
async def update_clinic_settings(
    data: TenantUpdate,
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    tenant = await db.get(Tenant, current_user.tenant_id)
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tenant, field, value)
    await db.flush()
    return tenant


@router.get("/cezih-status", response_model=CezihStatusResponse)
async def get_cezih_status(
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    tenant = await db.get(Tenant, current_user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Klinika nije pronađena")
    # Use the most recent heartbeat from any connected agent
    conn = agent_manager.get_any_connected(current_user.tenant_id)
    all_conns = agent_manager.get_all(current_user.tenant_id)
    latest_heartbeat = None
    for c in all_conns:
        if c.last_heartbeat and (latest_heartbeat is None or c.last_heartbeat > latest_heartbeat):
            latest_heartbeat = c.last_heartbeat
    return CezihStatusResponse(
        status=tenant.cezih_status,
        sifra_ustanove=tenant.sifra_ustanove,
        oid=tenant.oid,
        agent_connected=conn is not None,
        agents_count=len(all_conns),
        last_heartbeat=latest_heartbeat,
    )


class GenerateOidResponse(BaseModel):
    oid: str


@router.post("/generate-oid", response_model=GenerateOidResponse)
async def generate_oid(
    request: Request,
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id).with_for_update())
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Klinika nije pronađena")
    if tenant.oid:
        raise HTTPException(
            status_code=409,
            detail="OID je već generiran. Kontaktirajte podršku ako ga trebate promijeniti.",
        )
    if not tenant.sifra_ustanove:
        raise HTTPException(
            status_code=422,
            detail="Šifra ustanove mora biti postavljena prije generiranja OID-a. Unesite je u polje iznad.",
        )

    oid_result = await cezih_dispatcher.oid_generate(
        quantity=1,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=request.app.state.http_client,
    )
    generated_oid = oid_result.get("generated_oid", "")
    if not generated_oid:
        raise HTTPException(status_code=502, detail="CEZIH nije vratio OID. Pokušajte ponovno.")

    tenant.oid = generated_oid
    await db.commit()
    return GenerateOidResponse(oid=generated_oid)


class AgentSecretResponse(BaseModel):
    agent_secret: str
    tenant_id: str


@router.post("/generate-agent-secret", response_model=AgentSecretResponse)
async def generate_agent_secret(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = await db.get(Tenant, current_user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Klinika nije pronađena")

    # Disconnect all agents before changing the secret to prevent orphaned connections
    all_conns = agent_manager.get_all(current_user.tenant_id)
    for conn in all_conns:
        try:
            await conn.websocket.send_json(
                {
                    "type": "secret_changed",
                    "message": "Tajni ključ je promijenjen. Ponovno uparivanje je potrebno.",
                }
            )
        except Exception:
            pass
    for conn in all_conns:
        await agent_manager.disconnect(current_user.tenant_id, conn.agent_id)

    secret = secrets.token_hex(32)
    tenant.agent_secret = secret
    await db.flush()
    return AgentSecretResponse(agent_secret=secret, tenant_id=str(tenant.id))


# --- Pairing token flow ---
# In-memory store: {token: {"tenant_id": str, "created_at": float}}
# Single-use, 15-minute TTL — sufficient for single-server MVP.
_pairing_tokens: dict[str, dict] = {}

PAIRING_TTL_SECONDS = 15 * 60  # 15 minutes
PAIRING_MAX_TOKENS = 100  # cap to prevent unbounded growth
DEEP_LINK_SCHEME = "hm-agent"


class PairingTokenResponse(BaseModel):
    pairing_url: str
    pairing_token: str


class PairClaimRequest(BaseModel):
    pairing_token: str


class PairClaimResponse(BaseModel):
    tenant_id: str
    agent_secret: str
    backend_url: str


def _cleanup_expired_tokens() -> None:
    """Remove expired pairing tokens and enforce max size cap."""
    now = time.time()
    expired = [t for t, v in _pairing_tokens.items() if now - v["created_at"] > PAIRING_TTL_SECONDS]
    for t in expired:
        _pairing_tokens.pop(t, None)
    # Evict oldest if still over cap
    while len(_pairing_tokens) > PAIRING_MAX_TOKENS:
        oldest = min(_pairing_tokens, key=lambda t: _pairing_tokens[t]["created_at"])
        _pairing_tokens.pop(oldest, None)


def _get_backend_ws_url() -> str:
    """Build the WebSocket URL agents should connect to."""
    if settings.is_production and settings.DOMAIN:
        return f"wss://{settings.DOMAIN}/"
    return f"ws://localhost:{settings.PORT}/"


@router.post("/pairing-token", response_model=PairingTokenResponse)
async def create_pairing_token(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a short-lived pairing token for agent deep-link connection."""
    tenant = await db.get(Tenant, current_user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Klinika nije pronađena")
    if not tenant.agent_secret:
        raise HTTPException(status_code=400, detail="Agent secret nije generiran. Generirajte ga prvo.")

    _cleanup_expired_tokens()

    token = secrets.token_hex(32)
    _pairing_tokens[token] = {
        "tenant_id": str(tenant.id),
        "created_at": time.time(),
    }
    backend_url = _get_backend_ws_url()
    pairing_url = f"{DEEP_LINK_SCHEME}://connect?token={token}&backend={quote(backend_url, safe='')}"
    return PairingTokenResponse(pairing_url=pairing_url, pairing_token=token)


@router.post("/pair/claim", response_model=PairClaimResponse)
@limiter.limit("5/minute")
async def claim_pairing_token(
    request: Request,
    data: PairClaimRequest,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint — agent exchanges a pairing token for tenant credentials.
    Single-use, time-limited. No auth required."""
    _cleanup_expired_tokens()

    entry = _pairing_tokens.pop(data.pairing_token, None)
    if not entry:
        raise HTTPException(
            status_code=410,
            detail="Pairing token nije valjan ili je istekao. Generirajte novi.",
        )

    if time.time() - entry["created_at"] > PAIRING_TTL_SECONDS:
        raise HTTPException(
            status_code=410,
            detail="Pairing token je istekao. Generirajte novi.",
        )

    tenant = await db.get(Tenant, entry["tenant_id"])
    if not tenant or not tenant.agent_secret:
        raise HTTPException(status_code=404, detail="Klinika nije pronađena")

    return PairClaimResponse(
        tenant_id=str(tenant.id),
        agent_secret=tenant.agent_secret,
        backend_url=_get_backend_ws_url(),
    )


class CardStatusResponse(BaseModel):
    agent_connected: bool
    agents_count: int = 0
    card_inserted: bool
    card_holder: str | None
    vpn_connected: bool
    matched_doctor_id: str | None = None
    matched_doctor_name: str | None = None


@router.get("/card-status", response_model=CardStatusResponse)
async def get_card_status_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current smart card and agent status scoped to the calling user."""
    status_data = get_card_status(current_user.tenant_id, current_user.card_holder_name)
    result = CardStatusResponse(
        agent_connected=status_data["agent_connected"],
        agents_count=status_data["agents_count"],
        card_inserted=status_data["my_card_inserted"],
        card_holder=status_data["card_holder"],
        vpn_connected=status_data["vpn_connected"],
    )

    # If this user's card is inserted, set matched doctor to self
    if status_data["my_card_inserted"] and status_data["card_holder"]:
        result.matched_doctor_id = str(current_user.id)
        result.matched_doctor_name = f"{current_user.titula or ''} {current_user.ime} {current_user.prezime}".strip()

    return result
