"""DTS (Dijagnostičko-Terapijski Postupci) code sync service.

Syncs DTS procedure codes from CEZIH terminology to local DB.

Two distinct paths, no silent fallback between them (per CLAUDE.md "No fallbacks"):
- seed_dts_from_bootstrap(): one-shot first-boot seed from bundled JSON when the
  table is empty. Used only by the startup scheduler.
- sync_dts_codes(): live sync from CEZIH ValueSet/$expand. Raises on failure.

Sync schedule: bootstrap-if-empty on startup, then CEZIH refresh monthly.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import async_session
from app.models.dts import DtsCode

logger = logging.getLogger(__name__)

BOOTSTRAP_PATH = Path(__file__).parent.parent.parent / "data" / "CodeSystem-DTS.json"

DTS_SYSTEM_URL = "http://fhir.cezih.hr/specifikacije/CodeSystem/DTS"
DTS_VERSION = "0.1.0"

_sync_task: asyncio.Task | None = None


async def sync_dts_codes() -> dict:
    """Sync DTS codes from CEZIH ValueSet/$expand. No fallback - raises on failure."""
    concepts = await _fetch_from_cezih()
    if not concepts:
        raise RuntimeError(
            "DTS sync: CEZIH ValueSet/$expand returned no concepts. "
            "Check CEZIH credentials, VPN, and terminology-services availability."
        )
    upserted = await _upsert_codes(concepts)
    logger.info("DTS sync complete: %d codes from CEZIH", upserted)
    return {"source": "cezih", "count": upserted}


async def seed_dts_from_bootstrap() -> dict:
    """One-shot seed from bundled CodeSystem-DTS.json. For first-boot only."""
    concepts = _load_bootstrap()
    if not concepts:
        raise RuntimeError(f"DTS bootstrap: no concepts loaded from {BOOTSTRAP_PATH}")
    upserted = await _upsert_codes(concepts)
    logger.info("DTS bootstrap seed complete: %d codes", upserted)
    return {"source": "bootstrap", "count": upserted}


async def search_dts(query: str, limit: int = 20) -> list[dict]:
    """Search local DTS codes by code prefix or display name."""
    async with async_session() as db:
        q = query.strip().lower()
        if not q:
            return []

        stmt = (
            select(DtsCode)
            .where(
                DtsCode.aktivan.is_(True),
                DtsCode.search_text.ilike(f"%{q}%"),
            )
            .order_by(
                DtsCode.code.ilike(f"{q}%").desc(),
                DtsCode.code,
            )
            .limit(limit)
        )
        result = await db.execute(stmt)
        return [
            {"code": r.code, "display": r.display, "system": r.system, "version": r.version}
            for r in result.scalars().all()
        ]


async def get_dts_count() -> int:
    """Return number of DTS codes in local DB."""
    async with async_session() as db:
        result = await db.execute(select(func.count(DtsCode.id)))
        return result.scalar() or 0


async def _fetch_from_cezih() -> list[dict]:
    """Fetch DTS codes from CEZIH ValueSet/$expand. Raises on failure - no silent fallback."""
    import httpx

    from app.config import settings
    from app.services.cezih.client import CezihFhirClient

    if not settings.CEZIH_CLIENT_ID:
        raise RuntimeError("DTS sync: CEZIH_CLIENT_ID not configured")

    async with httpx.AsyncClient(timeout=30.0) as client:
        fhir_client = CezihFhirClient(client)
        resp = await fhir_client.get(
            "terminology-services/api/v1/ValueSet/$expand",
            params={
                "url": "http://fhir.cezih.hr/specifikacije/ValueSet/postupci",
                "_count": "20000",
            },
        )
        concepts = []
        for c in resp.get("expansion", {}).get("contains", []):
            concepts.append(
                {
                    "code": c.get("code", ""),
                    "display": c.get("display", ""),
                    "system": c.get("system", DTS_SYSTEM_URL),
                    "version": c.get("version", DTS_VERSION),
                }
            )
        logger.info("DTS sync: fetched %d codes from CEZIH", len(concepts))
        return concepts


def _load_bootstrap() -> list[dict]:
    """Load DTS codes from bootstrap JSON file."""
    if not BOOTSTRAP_PATH.exists():
        logger.warning("DTS bootstrap file not found: %s", BOOTSTRAP_PATH)
        return []

    try:
        data = json.loads(BOOTSTRAP_PATH.read_text(encoding="utf-8"))
        concepts = []
        for c in data.get("concept", []):
            concepts.append(
                {
                    "code": c.get("code", ""),
                    "display": c.get("display", ""),
                    "system": data.get("url", DTS_SYSTEM_URL),
                    "version": data.get("version", DTS_VERSION),
                }
            )
        logger.info("DTS bootstrap: loaded %d codes from %s", len(concepts), BOOTSTRAP_PATH.name)
        return concepts
    except Exception:
        logger.exception("DTS bootstrap load failed")
        return []


async def _upsert_codes(concepts: list[dict]) -> int:
    """Upsert DTS codes into DB. Returns number of upserted rows."""
    now = datetime.now(UTC)
    batch_size = 500
    upserted = 0

    async with async_session() as db:
        for i in range(0, len(concepts), batch_size):
            batch = []
            for c in concepts[i : i + batch_size]:
                code = c["code"]
                display = c["display"]
                batch.append(
                    {
                        "code": code,
                        "display": display,
                        "system": c.get("system", DTS_SYSTEM_URL),
                        "version": c.get("version", DTS_VERSION),
                        "aktivan": True,
                        "synced_at": now,
                        "search_text": f"{code.lower()} {display.lower()}",
                    }
                )

            stmt = pg_insert(DtsCode).values(batch)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_dts_code",
                set_={
                    "display": stmt.excluded.display,
                    "system": stmt.excluded.system,
                    "version": stmt.excluded.version,
                    "aktivan": True,
                    "synced_at": stmt.excluded.synced_at,
                    "search_text": stmt.excluded.search_text,
                },
            )
            await db.execute(stmt)
            upserted += len(batch)

        await db.commit()
    return upserted


async def _is_sync_fresh(max_days: int = 30) -> bool:
    """Check if DTS data was synced within the last N days."""
    async with async_session() as db:
        result = await db.execute(select(func.max(DtsCode.synced_at)))
        last_sync = result.scalar()
        if last_sync is None:
            return False
        age = datetime.now(UTC) - last_sync  # type: ignore[operator]
        return age.days < max_days


async def _sync_loop():
    """Bootstrap-if-empty on startup, then CEZIH refresh monthly.

    Bootstrap runs once when the table is empty (e.g. fresh deploy). CEZIH sync
    runs monthly thereafter. The two are NOT fallbacks for each other - if CEZIH
    sync fails after bootstrap, the error is logged but bootstrap data stays.
    """
    await asyncio.sleep(12)  # Wait for DB to be ready (stagger from ICD-10)

    # First-boot seed: if the table is empty, load from bundled JSON.
    try:
        if await get_dts_count() == 0:
            result = await seed_dts_from_bootstrap()
            logger.info("DTS initial bootstrap: %s", result)
    except Exception:
        logger.exception("DTS bootstrap seed failed")

    # Try a live CEZIH sync on startup if data is stale (does not block on failure).
    try:
        if not await _is_sync_fresh():
            result = await sync_dts_codes()
            logger.info("DTS initial CEZIH sync: %s", result)
        else:
            count = await get_dts_count()
            logger.info("DTS sync skipped - data is fresh (%d codes, < 30 days)", count)
    except Exception:
        logger.exception("DTS initial CEZIH sync failed - keeping existing data")

    while True:
        await asyncio.sleep(30 * 24 * 3600)
        try:
            result = await sync_dts_codes()
            logger.info("DTS monthly sync: %s", result)
        except Exception:
            logger.exception("DTS monthly sync failed - keeping existing data")


def start_dts_sync_scheduler():
    """Start the background DTS sync loop."""
    global _sync_task
    _sync_task = asyncio.create_task(_sync_loop())
    logger.info("DTS sync scheduler started (monthly)")


def stop_dts_sync_scheduler():
    """Cancel the background DTS sync loop."""
    global _sync_task
    if _sync_task and not _sync_task.done():
        _sync_task.cancel()
        logger.info("DTS sync scheduler stopped")
