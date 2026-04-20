"""One-time backfill: populate cezih_document_oid for records missing it.

Run on production:
  docker compose exec backend python backfill_oids.py
"""
import asyncio
import base64
import logging

from urllib.parse import urlparse, parse_qs

from app.database import async_session
from app.models.medical_record import MedicalRecord
from app.models.patient import Patient
from app.services.cezih.client import CezihFhirClient, current_tenant_id
from sqlalchemy import select
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MBO_SYSTEM = "http://fhir.cezih.hr/specifikacije/identifikatori/MBO"

# Default tenant for CEZIH operations (HM Digital test tenant)
DEFAULT_TENANT_ID = "11111111-1111-1111-1111-111111111111"


def _extract_oid_from_doc(doc_ref: dict) -> str:
    for content in doc_ref.get("content", []):
        url = content.get("attachment", {}).get("url", "")
        if not url:
            continue
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        data_val = qs.get("data", [""])[0]
        if data_val:
            decoded = base64.b64decode(data_val).decode("utf-8", errors="replace")
            for part in decoded.split("&"):
                if part.startswith("documentUniqueId="):
                    uid = part.split("=", 1)[1]
                    if "|" in uid:
                        oid = uid.split("|", 1)[1]
                        if oid.startswith("urn:oid:"):
                            return oid
    master_id = doc_ref.get("masterIdentifier", {})
    val = master_id.get("value", "")
    if val.startswith("urn:oid:"):
        return val
    return ""


async def backfill():
    current_tenant_id.set(DEFAULT_TENANT_ID)

    async with async_session() as db:
        result = await db.execute(
            select(MedicalRecord).where(
                MedicalRecord.cezih_reference_id.isnot(None),
                MedicalRecord.cezih_document_oid.is_(None),
            )
        )
        records = result.scalars().all()
        if not records:
            logger.info("No records need OID backfill.")
            return

        logger.info("Found %d records needing OID backfill.", len(records))

        # Group by patient to batch ITI-67 lookups
        patient_mbos: dict[str, list[MedicalRecord]] = {}
        records_no_mbo: list[MedicalRecord] = []
        for rec in records:
            if not rec.patient_id:
                records_no_mbo.append(rec)
                continue
            patient = await db.get(Patient, rec.patient_id)
            if not patient or not patient.mbo:
                records_no_mbo.append(rec)
                continue
            patient_mbos.setdefault(patient.mbo, []).append(rec)

        if records_no_mbo:
            logger.warning(
                "%d records have no patient/MBO — cannot backfill: %s",
                len(records_no_mbo),
                [r.cezih_reference_id for r in records_no_mbo],
            )

        async with httpx.AsyncClient() as http_client:
            fhir_client = CezihFhirClient(http_client, tenant_id=DEFAULT_TENANT_ID)

            for mbo, recs in patient_mbos.items():
                logger.info("Looking up OIDs for patient MBO=%s (%d docs)...", mbo, len(recs))
                ref_ids = {r.cezih_reference_id for r in recs}
                ref_to_record: dict[str, MedicalRecord] = {r.cezih_reference_id: r for r in recs}

                found = 0
                for status_filter in ["current", "superseded"]:
                    if found >= len(recs):
                        break
                    try:
                        response = await fhir_client.get(
                            "doc-mhd-svc/api/v1/DocumentReference",
                            params={
                                "patient.identifier": f"{MBO_SYSTEM}|{mbo}",
                                "status": status_filter,
                            },
                        )
                        if isinstance(response, bytes):
                            logger.warning("Got binary response, skipping")
                            continue
                    except Exception as e:
                        logger.warning("ITI-67 search failed for MBO=%s status=%s: %s", mbo, status_filter, e)
                        continue

                    for entry in response.get("entry", []):
                        doc_ref = entry.get("resource", {})
                        doc_id = doc_ref.get("id", "")
                        if doc_id in ref_ids and doc_id in ref_to_record:
                            oid = _extract_oid_from_doc(doc_ref)
                            if oid:
                                record = ref_to_record[doc_id]
                                record.cezih_document_oid = oid
                                del ref_to_record[doc_id]
                                found += 1
                                logger.info("  %s -> %s (status=%s)", doc_id, oid, status_filter)

                if ref_to_record:
                    logger.warning(
                        "  Could not resolve OIDs for: %s",
                        list(ref_to_record.keys()),
                    )

                await db.flush()

        await db.commit()
        logger.info("Backfill complete.")


if __name__ == "__main__":
    asyncio.run(backfill())
