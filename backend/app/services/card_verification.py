from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.agent_connection_manager import agent_manager


async def verify_card_matches_doctor(
    tenant_id: UUID,
    user_id: UUID,
    db: AsyncSession,
) -> tuple[bool, str]:
    """Check if the currently inserted card matches the given doctor."""
    conn = agent_manager.get(tenant_id)
    if not conn:
        return False, "Agent nije spojen"

    if not conn.card_inserted:
        return False, "Kartica nije umetnuta"

    user = await db.get(User, user_id)
    if not user:
        return False, "Korisnik nije pronađen"

    if not user.card_holder_name:
        return False, "Doktor nema povezanu karticu"

    if not conn.card_holder:
        return False, "Kartica nema podatke o nositelju"

    if conn.card_holder.strip().upper() != user.card_holder_name.strip().upper():
        return False, f"Umetnuta kartica ({conn.card_holder}) ne pripada ovom doktoru"

    return True, "OK"


def get_card_status(tenant_id: UUID) -> dict:
    """Get current card/agent status for a tenant."""
    conn = agent_manager.get(tenant_id)
    if not conn:
        return {
            "agent_connected": False,
            "card_inserted": False,
            "card_holder": None,
            "vpn_connected": False,
        }
    return {
        "agent_connected": True,
        "card_inserted": conn.card_inserted,
        "card_holder": conn.card_holder,
        "vpn_connected": conn.vpn_connected,
    }
