"""ICD-10 HR (MKB-10) code sync service.

Syncs ICD-10 diagnosis codes from CEZIH terminology service to local DB.
Falls back to bootstrap JSON file if CEZIH doesn't return data.

Sync schedule: on startup (if stale) + monthly cron.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import async_session
from app.models.icd10 import Icd10Code

logger = logging.getLogger(__name__)

# Bootstrap file from Simplifier cezih.hr.cezih-osnova v0.2.9
BOOTSTRAP_PATH = Path(__file__).parent.parent.parent / "data" / "CodeSystem-icd10-hr.json"

ICD10_SYSTEM_URL = "http://fhir.cezih.hr/specifikacije/CodeSystem/icd10-hr"

_sync_task: asyncio.Task | None = None


async def sync_icd10_codes() -> dict:
    """Sync ICD-10 codes: try CEZIH first, fall back to bootstrap JSON.

    Returns summary dict with counts.
    """
    concepts = await _fetch_from_cezih()
    source = "cezih"

    if not concepts:
        concepts = _load_bootstrap()
        source = "bootstrap"

    if not concepts:
        logger.warning("ICD-10 sync: no data from CEZIH or bootstrap")
        return {"source": "none", "count": 0}

    upserted = await _upsert_codes(concepts)
    logger.info("ICD-10 sync complete: %d codes from %s", upserted, source)
    return {"source": source, "count": upserted}


async def search_icd10(query: str, limit: int = 20) -> list[dict]:
    """Search local ICD-10 codes by code prefix or display name."""
    async with async_session() as db:
        q = query.strip().lower()
        if not q:
            return []

        # Use trigram search for display name, prefix match for codes
        stmt = (
            select(Icd10Code)
            .where(
                Icd10Code.aktivan.is_(True),
                Icd10Code.search_text.ilike(f"%{q}%"),
            )
            .order_by(
                # Exact code prefix first, then by code
                Icd10Code.code.ilike(f"{q}%").desc(),
                Icd10Code.code,
            )
            .limit(limit)
        )
        result = await db.execute(stmt)
        return [
            {"code": r.code, "display": r.display, "system": r.system}
            for r in result.scalars().all()
        ]


async def get_icd10_count() -> int:
    """Return number of ICD-10 codes in local DB."""
    async with async_session() as db:
        result = await db.execute(select(func.count(Icd10Code.id)))
        return result.scalar() or 0


async def _fetch_from_cezih() -> list[dict]:
    """Try to fetch ICD-10 codes from CEZIH ValueSet/$expand."""
    try:
        import httpx

        from app.config import settings
        from app.services.cezih.client import CezihFhirClient

        if not settings.CEZIH_CLIENT_ID:
            logger.info("ICD-10 sync: CEZIH credentials not configured, skipping")
            return []

        async with httpx.AsyncClient(timeout=30.0) as client:
            fhir_client = CezihFhirClient(client)
            # Try ValueSet/$expand
            resp = await fhir_client.get(
                "terminology-services/api/v1/ValueSet/$expand",
                params={
                    "url": "http://fhir.cezih.hr/specifikacije/ValueSet/icd10-hr",
                    "_count": "20000",
                },
            )
            concepts = []
            for c in resp.get("expansion", {}).get("contains", []):
                concepts.append({
                    "code": c.get("code", ""),
                    "display": c.get("display", ""),
                    "system": c.get("system", ICD10_SYSTEM_URL),
                })
            if concepts:
                logger.info("ICD-10 sync: fetched %d codes from CEZIH", len(concepts))
            return concepts
    except Exception as e:
        logger.info("ICD-10 sync: CEZIH fetch failed (%s), will use bootstrap", e)
        return []


def _load_bootstrap() -> list[dict]:
    """Load ICD-10 codes from bootstrap JSON file."""
    if not BOOTSTRAP_PATH.exists():
        logger.warning("ICD-10 bootstrap file not found: %s", BOOTSTRAP_PATH)
        return []

    try:
        data = json.loads(BOOTSTRAP_PATH.read_text(encoding="utf-8"))
        concepts = []
        for c in data.get("concept", []):
            concepts.append({
                "code": c.get("code", ""),
                "display": c.get("display", ""),
                "system": data.get("url", ICD10_SYSTEM_URL),
            })
        logger.info("ICD-10 bootstrap: loaded %d codes from %s", len(concepts), BOOTSTRAP_PATH.name)
        return concepts
    except Exception:
        logger.exception("ICD-10 bootstrap load failed")
        return []


async def _upsert_codes(concepts: list[dict]) -> int:
    """Upsert ICD-10 codes into DB. Returns number of upserted rows."""
    now = datetime.now(UTC)
    batch_size = 500
    upserted = 0

    async with async_session() as db:
        for i in range(0, len(concepts), batch_size):
            batch = []
            for c in concepts[i : i + batch_size]:
                code = c["code"]
                display = c["display"]
                batch.append({
                    "code": code,
                    "display": display,
                    "system": c.get("system", ICD10_SYSTEM_URL),
                    "aktivan": True,
                    "synced_at": now,
                    "search_text": f"{code.lower()} {display.lower()}",
                })

            stmt = pg_insert(Icd10Code).values(batch)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_icd10_code",
                set_={
                    "display": stmt.excluded.display,
                    "system": stmt.excluded.system,
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
    """Check if ICD-10 data was synced within the last N days."""
    async with async_session() as db:
        result = await db.execute(
            select(func.max(Icd10Code.synced_at))
        )
        last_sync = result.scalar()
        if last_sync is None:
            return False
        age = datetime.now(UTC) - last_sync  # type: ignore[operator]
        return age.days < max_days


async def _sync_loop():
    """Run sync on startup (if stale), then monthly."""
    await asyncio.sleep(10)  # Wait for DB to be ready

    try:
        if await _is_sync_fresh():
            count = await get_icd10_count()
            logger.info("ICD-10 sync skipped — data is fresh (%d codes, < 30 days)", count)
        else:
            result = await sync_icd10_codes()
            logger.info("ICD-10 initial sync: %s", result)
    except Exception:
        logger.exception("ICD-10 initial sync failed")

    # Monthly loop
    while True:
        await asyncio.sleep(30 * 24 * 3600)  # 30 days
        try:
            result = await sync_icd10_codes()
            logger.info("ICD-10 monthly sync: %s", result)
        except Exception:
            logger.exception("ICD-10 monthly sync failed")


def start_icd10_sync_scheduler():
    """Start the background ICD-10 sync loop."""
    global _sync_task
    _sync_task = asyncio.create_task(_sync_loop())
    logger.info("ICD-10 sync scheduler started (monthly)")


def stop_icd10_sync_scheduler():
    """Cancel the background ICD-10 sync loop."""
    global _sync_task
    if _sync_task and not _sync_task.done():
        _sync_task.cancel()
        logger.info("ICD-10 sync scheduler stopped")
