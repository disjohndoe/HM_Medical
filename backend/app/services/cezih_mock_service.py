import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.cezih_euputnica import CezihEUputnica
from app.models.medical_record import MedicalRecord

_MOCK_NAMES = [
    ("Ivan", "Horvat", "1985-03-15"),
    ("Ana", "Kovačević", "1990-07-22"),
    ("Marko", "Marić", "1978-11-08"),
    ("Petra", "Jurić", "1995-01-30"),
    ("Luka", "Novak", "1982-09-12"),
]

_MOCK_OSIGURAVATELJI = ["HZZO", "HZZO", "HZZO", "Adria Osiguranje", "CROATIA osiguranje"]
_MOCK_STATUS = ["Aktivan", "Aktivan", "Aktivan", "Aktivan", "Na čekanju"]


def _deterministic_index(mbo: str) -> int:
    return int(hashlib.md5(mbo.encode()).hexdigest(), 16) % len(_MOCK_NAMES)


async def _write_audit(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    action: str,
    resource_id: UUID | None = None,
    details: dict | None = None,
) -> None:
    entry = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        resource_type="cezih",
        resource_id=resource_id,
        details=json.dumps(details, default=str) if details else None,
    )
    db.add(entry)
    await db.flush()


async def mock_insurance_check(
    mbo: str,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    idx = _deterministic_index(mbo)
    name = _MOCK_NAMES[idx]

    result = {
        "mock": True,
        "mbo": mbo,
        "ime": name[0],
        "prezime": name[1],
        "datum_rodjenja": name[2],
        "osiguravatelj": _MOCK_OSIGURAVATELJI[idx],
        "status_osiguranja": _MOCK_STATUS[idx],
        "broj_osiguranja": f"HR-{mbo[-6:]}",
    }

    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="insurance_check",
            details={"mbo": mbo, "result": result["status_osiguranja"]},
        )

    return result


async def mock_send_enalaz(
    db: AsyncSession,
    tenant_id: UUID,
    patient_id: UUID,
    record_id: UUID,
    user_id: UUID | None = None,
    uputnica_id: str | None = None,
) -> dict:
    import os

    ref = f"MOCK-EN-{os.urandom(4).hex()}"
    now = datetime.now(UTC)

    result = await db.execute(
        select(MedicalRecord).where(
            MedicalRecord.id == record_id,
            MedicalRecord.tenant_id == tenant_id,
            MedicalRecord.patient_id == patient_id,
        )
    )
    record = result.scalar_one_or_none()
    if record:
        record.cezih_sent = True
        record.cezih_sent_at = now
        record.cezih_reference_id = ref
        await db.flush()

    # Close the linked referral in the DB if provided
    if uputnica_id:
        uputnica_result = await db.execute(
            select(CezihEUputnica).where(
                CezihEUputnica.tenant_id == tenant_id,
                CezihEUputnica.external_id == uputnica_id,
            )
        )
        uputnica_row = uputnica_result.scalar_one_or_none()
        if uputnica_row:
            uputnica_row.status = "Zatvorena"
            await db.flush()

    details: dict = {
        "patient_id": str(patient_id),
        "record_id": str(record_id),
        "reference_id": ref,
    }
    if uputnica_id:
        details["uputnica_id"] = uputnica_id

    if user_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="e_nalaz_send",
            resource_id=patient_id,
            details=details,
        )

    return {
        "mock": True,
        "success": True,
        "reference_id": ref,
        "sent_at": now.isoformat(),
    }


_MOCK_EUPUTNICE = [
    {
        "external_id": "EU-2026-001",
        "datum_izdavanja": "2026-03-15",
        "izdavatelj": "DOM ZDRAVLJA ZAGREB-CENTAR",
        "svrha": "Kardiološki pregled",
        "specijalist": "Dr. sc. med. Josip Babić, dr. med.",
        "status": "Otvorena",
    },
    {
        "external_id": "EU-2026-002",
        "datum_izdavanja": "2026-03-10",
        "izdavatelj": "DOM ZDRAVLJA SPLIT",
        "svrha": "Dermatološka pretraga",
        "specijalist": "Prof. dr. sc. Marija Perić",
        "status": "Zatvorena",
    },
    {
        "external_id": "EU-2026-003",
        "datum_izdavanja": "2026-03-20",
        "izdavatelj": "POLIKLINIKA RIJEKA",
        "svrha": "Ortopedska konzultacija",
        "specijalist": "Dr. Ante Tomić, dr. med.",
        "status": "Otvorena",
    },
    {
        "external_id": "EU-2026-004",
        "datum_izdavanja": "2026-03-24",
        "izdavatelj": "KBC ZAGREB",
        "svrha": "Neurološki pregled",
        "specijalist": "Dr. sc. Ivan Matić, dr. med.",
        "status": "Otvorena",
    },
    {
        "external_id": "EU-2026-005",
        "datum_izdavanja": "2026-03-25",
        "izdavatelj": "DOM ZDRAVLJA OSIJEK",
        "svrha": "Oftalmološki pregled",
        "specijalist": "Dr. Lana Herceg, dr. med.",
        "status": "Otvorena",
    },
]


async def mock_retrieve_euputnice(
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    """Fetch new e-Uputnice from CEZIH (mock) and persist them.

    Existing referrals are updated; new ones are inserted.
    Returns only the newly fetched batch (for the toast count).
    """
    new_count = 0

    if db and tenant_id:
        # Determine which referrals should be closed (e-Nalaz linked)
        nalaz_result = await db.execute(
            select(AuditLog.details).where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.resource_type == "cezih",
                AuditLog.action == "e_nalaz_send",
            )
        )
        closed_ids: set[str] = set()
        for (details_str,) in nalaz_result.all():
            if details_str:
                details = json.loads(details_str)
                uid = details.get("uputnica_id")
                if uid:
                    closed_ids.add(uid)

        # Upsert each mock referral into the DB
        for item in _MOCK_EUPUTNICE:
            ext_id = item["external_id"]
            status = "Zatvorena" if ext_id in closed_ids or item["status"] == "Zatvorena" else "Otvorena"

            existing = await db.execute(
                select(CezihEUputnica).where(
                    CezihEUputnica.tenant_id == tenant_id,
                    CezihEUputnica.external_id == ext_id,
                )
            )
            row = existing.scalar_one_or_none()
            if row:
                # Update status if changed
                row.status = status
            else:
                db.add(CezihEUputnica(
                    tenant_id=tenant_id,
                    external_id=ext_id,
                    datum_izdavanja=item["datum_izdavanja"],
                    izdavatelj=item["izdavatelj"],
                    svrha=item["svrha"],
                    specijalist=item["specijalist"],
                    status=status,
                ))
                new_count += 1

        await db.flush()

    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="e_uputnica_retrieve",
            details={"count": len(_MOCK_EUPUTNICE), "new": new_count},
        )

    # Return the full persisted list
    return await get_stored_euputnice(db, tenant_id)


async def get_stored_euputnice(
    db: AsyncSession | None,
    tenant_id: UUID | None,
) -> dict:
    """Read all persisted e-Uputnice for the tenant."""
    if not db or not tenant_id:
        return {"mock": True, "items": []}

    result = await db.execute(
        select(CezihEUputnica)
        .where(CezihEUputnica.tenant_id == tenant_id)
        .order_by(CezihEUputnica.datum_izdavanja.desc())
    )
    rows = result.scalars().all()

    items = [
        {
            "mock": True,
            "id": r.external_id,
            "datum_izdavanja": r.datum_izdavanja,
            "izdavatelj": r.izdavatelj,
            "svrha": r.svrha,
            "specijalist": r.specijalist,
            "status": r.status,
        }
        for r in rows
    ]
    return {"mock": True, "items": items}


async def mock_send_erecept(
    patient_id: UUID,
    lijekovi: list[dict],
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    import os

    recept_id = f"MOCK-ER-{os.urandom(4).hex()}"

    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="e_recept_send",
            resource_id=patient_id,
            details={
                "patient_id": str(patient_id),
                "recept_id": recept_id,
                "lijekovi": [item.get("naziv", "") if isinstance(item, dict) else str(item) for item in lijekovi],
            },
        )

    return {
        "mock": True,
        "success": True,
        "recept_id": recept_id,
    }


async def mock_cancel_erecept(
    recept_id: str,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="e_recept_cancel",
            details={"recept_id": recept_id},
        )
    return {
        "mock": True,
        "success": True,
        "recept_id": recept_id,
        "status": "storniran",
    }


def mock_cezih_status(tenant_id=None) -> dict:
    from app.services.agent_connection_manager import agent_manager

    agent_connected = False
    last_heartbeat = None
    if tenant_id:
        agent_connected = agent_manager.is_connected(tenant_id)
        conn = agent_manager.get(tenant_id)
        if conn:
            last_heartbeat = conn.last_heartbeat

    return {
        "mock": True,
        "connected": False,
        "mode": "mock",
        "agent_connected": agent_connected,
        "last_heartbeat": last_heartbeat,
    }


# --- Feature 4: Mock Drug List ---

MOCK_LIJEKOVI = [
    {"atk": "N02BE01", "naziv": "Paracetamol 500mg", "oblik": "tableta", "jacina": "500 mg"},
    {"atk": "N02BA01", "naziv": "Aspirin 500mg", "oblik": "tableta", "jacina": "500 mg"},
    {"atk": "M01AE01", "naziv": "Ibuprofen 400mg", "oblik": "tableta", "jacina": "400 mg"},
    {"atk": "M01AE01", "naziv": "Ibuprofen 600mg", "oblik": "tableta", "jacina": "600 mg"},
    {"atk": "N02AX02", "naziv": "Tramadol 50mg", "oblik": "kapsula", "jacina": "50 mg"},
    {"atk": "C07AB02", "naziv": "Metoprolol 50mg", "oblik": "tableta", "jacina": "50 mg"},
    {"atk": "C09AA02", "naziv": "Enalapril 10mg", "oblik": "tableta", "jacina": "10 mg"},
    {"atk": "C09AA05", "naziv": "Ramipril 5mg", "oblik": "tableta", "jacina": "5 mg"},
    {"atk": "C10AA05", "naziv": "Atorvastatin 20mg", "oblik": "tableta", "jacina": "20 mg"},
    {"atk": "C10AA01", "naziv": "Simvastatin 20mg", "oblik": "tableta", "jacina": "20 mg"},
    {"atk": "A02BC01", "naziv": "Omeprazol 20mg", "oblik": "kapsula", "jacina": "20 mg"},
    {"atk": "A02BC02", "naziv": "Pantoprazol 40mg", "oblik": "tableta", "jacina": "40 mg"},
    {"atk": "J01CA04", "naziv": "Amoksicilin 500mg", "oblik": "kapsula", "jacina": "500 mg"},
    {"atk": "J01CR02", "naziv": "Amoksicilin + klavulanska kiselina 1g", "oblik": "tableta", "jacina": "875/125 mg"},
    {"atk": "J01FA10", "naziv": "Azitromicin 500mg", "oblik": "tableta", "jacina": "500 mg"},
    {"atk": "J01MA02", "naziv": "Ciprofloksacin 500mg", "oblik": "tableta", "jacina": "500 mg"},
    {"atk": "A10BA02", "naziv": "Metformin 850mg", "oblik": "tableta", "jacina": "850 mg"},
    {"atk": "A10BA02", "naziv": "Metformin 1000mg", "oblik": "tableta", "jacina": "1000 mg"},
    {"atk": "C03CA01", "naziv": "Furosemid 40mg", "oblik": "tableta", "jacina": "40 mg"},
    {"atk": "B01AC06", "naziv": "Acetilsalicilna kiselina 100mg", "oblik": "tableta", "jacina": "100 mg"},
    {"atk": "N05BA01", "naziv": "Diazepam 5mg", "oblik": "tableta", "jacina": "5 mg"},
    {"atk": "N06AB06", "naziv": "Sertralin 50mg", "oblik": "tableta", "jacina": "50 mg"},
    {"atk": "N06AB04", "naziv": "Citalopram 20mg", "oblik": "tableta", "jacina": "20 mg"},
    {"atk": "R06AE07", "naziv": "Cetirizin 10mg", "oblik": "tableta", "jacina": "10 mg"},
    {"atk": "R06AX13", "naziv": "Loratadin 10mg", "oblik": "tableta", "jacina": "10 mg"},
    {"atk": "H02AB06", "naziv": "Prednizon 5mg", "oblik": "tableta", "jacina": "5 mg"},
    {"atk": "H02AB04", "naziv": "Metilprednizolon 4mg", "oblik": "tableta", "jacina": "4 mg"},
    {"atk": "C08CA01", "naziv": "Amlodipin 5mg", "oblik": "tableta", "jacina": "5 mg"},
    {"atk": "C09DA01", "naziv": "Losartan 50mg", "oblik": "tableta", "jacina": "50 mg"},
    {"atk": "R03AC02", "naziv": "Salbutamol 100mcg", "oblik": "inhalator", "jacina": "100 mcg/doza"},
]


def mock_drug_search(query: str) -> list[dict]:
    if not query or len(query) < 2:
        return []
    q = query.lower()
    return [d for d in MOCK_LIJEKOVI if q in d["naziv"].lower() or q in d["atk"].lower()]


# --- Mock Signing ---


def mock_sign_document(document_id: str | None = None) -> dict:
    """Mock remote document signing — returns a fake base64-encoded signature."""
    import base64
    import os

    fake_sig = base64.b64encode(os.urandom(256)).decode("ascii")
    return {
        "mock": True,
        "success": True,
        "signature": fake_sig,
        "signing_algorithm": "SHA-256",
        "signed_at": datetime.now(UTC).isoformat(),
        "document_id": document_id,
    }


def mock_sign_health_check() -> dict:
    """Mock signing service health check."""
    return {
        "mock": True,
        "reachable": True,
        "reason": None,
    }


# ============================================================
# TC6: OID Registry Lookup (Mock)
# ============================================================

_MOCK_OIDS = {
    "1.2.3.4.5.6": {"name": "HM Digital Medical", "responsible_org": "HM DIGITAL d.o.o.", "status": "active"},
    "2.16.840.1.113883.2.22.1.1": {"name": "HZZO", "responsible_org": "HZZO", "status": "active"},
    "2.16.840.1.113883.2.22": {"name": "CEZIH", "responsible_org": "HZZO", "status": "active"},
}


async def mock_lookup_oid(
    oid: str,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    data = _MOCK_OIDS.get(oid, {"name": f"Unknown OID: {oid}", "responsible_org": "", "status": "unknown"})
    result = {"mock": True, "oid": oid, **data}
    if db and user_id and tenant_id:
        await _write_audit(db, tenant_id, user_id, action="oid_lookup", details={"oid": oid})
    return result


# ============================================================
# TC7: Code System Query (Mock, generalized)
# ============================================================

_MOCK_CODE_SYSTEMS: dict[str, list[dict]] = {
    "icd10-hr": [
        {"code": "J45", "display": "Astma", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/icd10-hr"},
        {"code": "M54", "display": "Dorsopatija", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/icd10-hr"},
        {"code": "I10", "display": "Esencijalna (primarna) hipertenzija", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/icd10-hr"},
        {"code": "E11", "display": "Šećerna bolest neovisan o inzulinu", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/icd10-hr"},
        {"code": "C00", "display": "Zloćudna novotvorina usne", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/icd10-hr"},
        {"code": "K29", "display": "Gastritis i duodenitis", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/icd10-hr"},
        {"code": "J06", "display": "Akutne infekcije gornjih dišnih puteva", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/icd10-hr"},
        {"code": "N39", "display": "Ostali poremećaji mokraćnog sustava", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/icd10-hr"},
        {"code": "F41", "display": "Ostali anksiozni poremećaji", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/icd10-hr"},
        {"code": "L20", "display": "Atopijski dermatitis", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/icd10-hr"},
    ],
    "nacin-prijema": [
        {"code": "1", "display": "Dnevna bolnica", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema"},
        {"code": "2", "display": "Hitan prijem", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema"},
        {"code": "3", "display": "Premještaj", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema"},
        {"code": "9", "display": "Interna uputnica", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema"},
    ],
}


async def mock_query_code_system(
    system_name: str,
    query: str,
    count: int = 20,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> list[dict]:
    codes = _MOCK_CODE_SYSTEMS.get(system_name, [])
    if query:
        q = query.lower()
        codes = [c for c in codes if q in c["code"].lower() or q in c["display"].lower()]
    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="code_system_query",
            details={"system": system_name, "query": query},
        )
    return [{"mock": True, **c} for c in codes[:count]]


# ============================================================
# TC8: Value Set Expand (Mock)
# ============================================================


async def mock_expand_value_set(
    url: str,
    filter_text: str | None = None,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    concepts = [
        {"code": "unconfirmed", "display": "Nepotvrđen", "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status"},
        {"code": "provisional", "display": "Privremeni", "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status"},
        {"code": "differential", "display": "Diferencijalni", "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status"},
        {"code": "confirmed", "display": "Potvrđen", "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status"},
    ]
    if filter_text:
        q = filter_text.lower()
        concepts = [c for c in concepts if q in c["display"].lower() or q in c["code"].lower()]
    if db and user_id and tenant_id:
        await _write_audit(db, tenant_id, user_id, action="value_set_expand", details={"url": url})
    return {"mock": True, "url": url, "concepts": concepts, "total": len(concepts)}


# ============================================================
# TC9: Subject Registry (Mock)
# ============================================================

_MOCK_ORGANIZATIONS: list[dict[str, str | bool]] = [
    {"id": "org-1", "name": "DOM ZDRAVLJA ZAGREB-CENTAR", "hzzo_code": "10001", "active": True},
    {"id": "org-2", "name": "KBC ZAGREB", "hzzo_code": "10002", "active": True},
    {"id": "org-3", "name": "POLIKLINIKA RIJEKA", "hzzo_code": "20001", "active": True},
    {"id": "org-4", "name": "DOM ZDRAVLJA SPLIT", "hzzo_code": "30001", "active": True},
    {"id": "org-5", "name": "DOM ZDRAVLJA OSIJEK", "hzzo_code": "40001", "active": True},
]

_MOCK_PRACTITIONERS: list[dict[str, str | bool]] = [
    {"id": "pract-1", "family": "Horvat", "given": "Josip", "hzjz_id": "1234567", "active": True},
    {"id": "pract-2", "family": "Perić", "given": "Marija", "hzjz_id": "2345678", "active": True},
    {"id": "pract-3", "family": "Tomić", "given": "Ante", "hzjz_id": "3456789", "active": True},
    {"id": "pract-4", "family": "Matić", "given": "Ivan", "hzjz_id": "4567890", "active": True},
    {"id": "pract-5", "family": "Herceg", "given": "Lana", "hzjz_id": "5678901", "active": True},
]


async def mock_find_organizations(
    name: str,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> list[dict]:
    q = name.lower()
    results = [o for o in _MOCK_ORGANIZATIONS if q in str(o["name"]).lower() or q in str(o["hzzo_code"])]
    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="organization_search",
            details={"name": name, "count": len(results)},
        )
    return [{"mock": True, **o} for o in results]


async def mock_find_practitioners(
    name: str,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> list[dict]:
    q = name.lower()
    results = [
        p for p in _MOCK_PRACTITIONERS
        if q in str(p["family"]).lower() or q in str(p["given"]).lower() or q in str(p["hzjz_id"])
    ]
    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="practitioner_search",
            details={"name": name, "count": len(results)},
        )
    return [{"mock": True, **p} for p in results]


# ============================================================
# TC11: Foreigner Registration (Mock)
# ============================================================


async def mock_register_foreigner(
    patient_data: dict,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    import os
    mock_mbo = f"F{os.urandom(4).hex().upper()}"
    result = {
        "mock": True,
        "success": True,
        "patient_id": f"mock-foreign-{os.urandom(4).hex()}",
        "mbo": mock_mbo,
    }
    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="foreigner_registration",
            details={"ime": patient_data.get("ime"), "prezime": patient_data.get("prezime"), "mbo": mock_mbo},
        )
    return result


# ============================================================
# TC12-14: Visit Management (Mock)
# ============================================================


async def mock_create_visit(
    patient_mbo: str,
    period_start: str,
    admission_type_code: str = "9",
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    import os
    visit_id = f"MOCK-V-{os.urandom(6).hex()}"
    result = {
        "mock": True,
        "success": True,
        "visit_id": visit_id,
        "status": "in-progress",
        "created_at": datetime.now(UTC).isoformat(),
    }
    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="visit_create",
            details={"mbo": patient_mbo, "visit_id": visit_id},
        )
    return result


async def mock_update_visit(
    visit_id: str,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
    **updates: str,
) -> dict:
    result = {"mock": True, "success": True, "visit_id": visit_id}
    if db and user_id and tenant_id:
        await _write_audit(db, tenant_id, user_id, action="visit_update", details={"visit_id": visit_id})
    return result


async def mock_close_visit(
    visit_id: str,
    period_end: str,
    diagnosis_case_id: str | None = None,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    result = {"mock": True, "success": True, "visit_id": visit_id, "status": "finished"}
    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="visit_close",
            details={"visit_id": visit_id, "period_end": period_end},
        )
    return result


async def mock_reopen_visit(
    visit_id: str,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    result = {"mock": True, "success": True, "visit_id": visit_id, "status": "in-progress"}
    if db and user_id and tenant_id:
        await _write_audit(db, tenant_id, user_id, action="visit_reopen", details={"visit_id": visit_id})
    return result


async def mock_cancel_visit(
    visit_id: str,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    result = {"mock": True, "success": True, "visit_id": visit_id, "status": "entered-in-error"}
    if db and user_id and tenant_id:
        await _write_audit(db, tenant_id, user_id, action="visit_cancel", details={"visit_id": visit_id})
    return result


# ============================================================
# TC15-17: Case Management (Mock)
# ============================================================

_MOCK_CASES = [
    {"case_id": "MOCK-C-001", "icd_code": "M54", "icd_display": "Dorsopatija",
     "clinical_status": "active", "onset_date": "2026-01-15"},
    {"case_id": "MOCK-C-002", "icd_code": "J45", "icd_display": "Astma",
     "clinical_status": "active", "onset_date": "2025-06-20"},
    {"case_id": "MOCK-C-003", "icd_code": "I10",
     "icd_display": "Esencijalna hipertenzija", "clinical_status": "remission",
     "onset_date": "2024-03-10"},
]


async def mock_retrieve_cases(
    patient_mbo: str,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> list[dict]:
    if db and user_id and tenant_id:
        await _write_audit(db, tenant_id, user_id, action="case_retrieve", details={"mbo": patient_mbo})
    return [{"mock": True, **c} for c in _MOCK_CASES]


async def mock_create_case(
    patient_mbo: str,
    icd_code: str,
    icd_display: str,
    onset_date: str,
    verification_status: str = "unconfirmed",
    note_text: str | None = None,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    import os
    local_id = f"local-{os.urandom(4).hex()}"
    cezih_id = f"MOCK-C-{os.urandom(6).hex()}"
    result = {
        "mock": True,
        "success": True,
        "local_case_id": local_id,
        "cezih_case_id": cezih_id,
    }
    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="case_create",
            details={"mbo": patient_mbo, "icd_code": icd_code, "case_id": cezih_id},
        )
    return result


async def mock_update_case(
    case_id: str,
    action: str,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    result = {"mock": True, "success": True, "case_id": case_id, "action": action}
    if db and user_id and tenant_id:
        await _write_audit(db, tenant_id, user_id, action=f"case_{action}", details={"case_id": case_id})
    return result


async def mock_update_case_data(
    case_id: str,
    updates: dict,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    result = {"mock": True, "success": True, "case_id": case_id}
    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="case_update_data",
            details={"case_id": case_id, "fields": list(updates.keys())},
        )
    return result


# ============================================================
# TC21: Flexible Document Search (Mock)
# ============================================================

_MOCK_DOCUMENTS = [
    {"id": "DOC-001", "datum_izdavanja": "2026-03-25",
     "izdavatelj": "DOM ZDRAVLJA ZAGREB-CENTAR", "svrha": "Kardiološki nalaz",
     "specijalist": "Dr. Babić", "status": "Otvorena", "type": "nalaz",
     "patient_mbo": "999990260"},
    {"id": "DOC-002", "datum_izdavanja": "2026-03-20",
     "izdavatelj": "KBC ZAGREB", "svrha": "RTG snimka",
     "specijalist": "Dr. Perić", "status": "Otvorena", "type": "nalaz",
     "patient_mbo": "999990260"},
    {"id": "DOC-003", "datum_izdavanja": "2026-03-15",
     "izdavatelj": "POLIKLINIKA RIJEKA", "svrha": "Laboratorijski nalaz",
     "specijalist": "Dr. Tomić", "status": "Zatvorena", "type": "nalaz",
     "patient_mbo": "999990261"},
    {"id": "DOC-004", "datum_izdavanja": "2026-03-10",
     "izdavatelj": "DOM ZDRAVLJA SPLIT", "svrha": "Dermatološki pregled",
     "specijalist": "Dr. Matić", "status": "Otvorena", "type": "uputnica",
     "patient_mbo": "999990260"},
    {"id": "DOC-005", "datum_izdavanja": "2026-03-05",
     "izdavatelj": "DOM ZDRAVLJA OSIJEK", "svrha": "Oftalmološka uputnica",
     "specijalist": "Dr. Herceg", "status": "Pogreška", "type": "uputnica",
     "patient_mbo": "999990262"},
]


async def mock_search_documents(
    patient_mbo: str | None = None,
    document_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status_filter: str | None = None,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> list[dict]:
    results = list(_MOCK_DOCUMENTS)
    if patient_mbo:
        results = [d for d in results if d["patient_mbo"] == patient_mbo]
    if document_type:
        results = [d for d in results if d["type"] == document_type]
    if date_from:
        results = [d for d in results if d["datum_izdavanja"] >= date_from]
    if date_to:
        results = [d for d in results if d["datum_izdavanja"] <= date_to]
    if status_filter:
        status_map = {"current": "Otvorena", "superseded": "Zatvorena", "entered-in-error": "Pogreška"}
        mapped = status_map.get(status_filter, status_filter)
        results = [d for d in results if d["status"] == mapped]
    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="document_search",
            details={"patient_mbo": patient_mbo, "type": document_type, "count": len(results)},
        )
    return [{"mock": True, **{k: v for k, v in d.items() if k != "patient_mbo"}} for d in results]


# ============================================================
# TC19-20, 22: Document Operations (Mock)
# ============================================================


async def mock_replace_document(
    original_reference_id: str,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    import os
    new_ref = f"MOCK-EN-R-{os.urandom(4).hex()}"
    result = {
        "mock": True, "success": True,
        "new_reference_id": new_ref, "replaced_reference_id": original_reference_id,
    }
    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="e_nalaz_replace",
            details={"original": original_reference_id, "new": new_ref},
        )
    return result


async def mock_cancel_document(
    reference_id: str,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    result = {"mock": True, "success": True, "reference_id": reference_id, "status": "entered-in-error"}
    if db and user_id and tenant_id:
        # Mark the medical record as storniran
        rec_result = await db.execute(
            select(MedicalRecord).where(
                MedicalRecord.cezih_reference_id == reference_id,
                MedicalRecord.tenant_id == tenant_id,
            )
        )
        record = rec_result.scalar_one_or_none()
        if record:
            record.cezih_storno = True
        await _write_audit(db, tenant_id, user_id, action="e_nalaz_cancel", details={"reference_id": reference_id})
    return result


async def mock_retrieve_document(
    reference_id: str,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> bytes:
    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="e_nalaz_retrieve_doc",
            details={"reference_id": reference_id},
        )
    return b"%PDF-1.4 mock document content for " + reference_id.encode()
