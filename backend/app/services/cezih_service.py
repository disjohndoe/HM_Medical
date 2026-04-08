import base64
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.medical_record import MedicalRecord

# HZZO official test patient (provisioned 2026-04-07)
_HZZO_PATIENT = ("GORAN", "PACPRIVATNICI19", "1980-01-01")
_HZZO_MBO = "999990260"
_HZZO_OIB = "99999900187"


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
    if mbo == _HZZO_MBO:
        name = _HZZO_PATIENT
    else:
        name = ("Nepoznat", "Pacijent", "1900-01-01")

    result = {
        "mock": True,
        "mbo": mbo,
        "ime": name[0],
        "prezime": name[1],
        "datum_rodjenja": name[2],
        "osiguravatelj": "HZZO",
        "status_osiguranja": "Aktivan",
        "broj_osiguranja": f"HR-{mbo[-6:]}",
    }

    patient_id = None
    if db and tenant_id:
        from sqlalchemy import select as sa_select
        from app.models.patient import Patient

        p_result = await db.execute(
            sa_select(Patient).where(Patient.tenant_id == tenant_id, Patient.mbo == mbo)
        )
        patient = p_result.scalar_one_or_none()
        if patient:
            patient.cezih_insurance_status = result["status_osiguranja"]
            patient.cezih_insurance_checked_at = datetime.now(UTC)
            patient_id = patient.id
            await db.flush()

    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="insurance_check",
            resource_id=patient_id,
            details={"mbo": mbo, "result": result["status_osiguranja"]},
        )

    return result


async def mock_send_enalaz(
    db: AsyncSession,
    tenant_id: UUID,
    patient_id: UUID,
    record_id: UUID,
    user_id: UUID | None = None,
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

    details: dict = {
        "patient_id": str(patient_id),
        "record_id": str(record_id),
        "reference_id": ref,
    }
    if record and record.preporucena_terapija:
        details["preporucena_terapija_count"] = len(record.preporucena_terapija)

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
        "signature_data": base64.b64encode(f"mock-signature-enalaz-{ref}".encode()).decode(),
        "signed_at": now.isoformat(),
    }


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
        conn = agent_manager.get_any_connected(tenant_id)
        if conn:
            last_heartbeat = conn.last_heartbeat

    return {
        "mock": True,
        "connected": False,
        "mode": "mock",
        "agent_connected": agent_connected,
        "last_heartbeat": last_heartbeat,
        "card_inserted": False,
        "vpn_connected": False,
        "reader_available": False,
        "card_holder": None,
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
    "1.2.162.1.999001464": {"name": "HM DIGITAL ordinacija", "responsible_org": "HM DIGITAL d.o.o.", "status": "active"},
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
        {"code": "1", "display": "Hitni prijem", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema"},
        {"code": "2", "display": "Uputnica PZZ", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema"},
        {"code": "3", "display": "Premještaj iz druge ustanove", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema"},
        {"code": "4", "display": "Nastavno liječenje", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema"},
        {"code": "5", "display": "Premještaj unutar ustanove", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema"},
        {"code": "6", "display": "Ostalo", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema"},
        {"code": "7", "display": "Poziv na raniji termin", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema"},
        {"code": "8", "display": "Telemedicina", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema"},
        {"code": "9", "display": "Interna uputnica", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema"},
        {"code": "10", "display": "Program+", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema"},
    ],
    "vrsta-posjete": [
        {"code": "1", "display": "Pacijent prisutan", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/vrsta-posjete"},
        {"code": "2", "display": "Pacijent udaljeno prisutan", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/vrsta-posjete"},
        {"code": "3", "display": "Pacijent nije prisutan", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/vrsta-posjete"},
    ],
    "hr-tip-posjete": [
        {"code": "1", "display": "Posjeta LOM", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/hr-tip-posjete"},
        {"code": "2", "display": "Posjeta SKZZ", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/hr-tip-posjete"},
        {"code": "3", "display": "Hospitalizacija", "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/hr-tip-posjete"},
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
    {"id": "org-0", "name": "HM DIGITAL ordinacija", "hzzo_code": "999001464", "active": True},
]

_MOCK_PRACTITIONERS: list[dict[str, str | bool]] = [
    {"id": "pract-0", "family": "TESTNIPREZIME55", "given": "TESTNI55", "hzjz_id": "7659059", "active": True},
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
            action="foreigner_register",
            details={"ime": patient_data.get("ime"), "prezime": patient_data.get("prezime"), "mbo": mock_mbo},
        )
    return result


# ============================================================
# TC12-14: Visit Management (Mock)
# ============================================================

_MOCK_VISITS: list[dict] = [
    {"visit_id": "MOCK-V-001", "patient_mbo": "999990260", "status": "in-progress",
     "visit_type": "6", "reason": "Kontrolni pregled", "period_start": "2026-04-07T08:00:00", "period_end": None},
    {"visit_id": "MOCK-V-002", "patient_mbo": "999990260", "status": "finished",
     "visit_type": "2", "reason": "Kardiološki pregled",
     "period_start": "2026-04-06T09:30:00",
     "period_end": "2026-04-06T10:15:00"},
]


async def mock_create_visit(
    patient_mbo: str,
    nacin_prijema: str = "6",
    reason: str | None = None,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    import os
    visit_id = f"MOCK-V-{os.urandom(4).hex()}"
    result = {
        "mock": True, "success": True,
        "visit_id": visit_id, "status": "in-progress",
    }
    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="visit_create",
            details={"mbo": patient_mbo, "visit_id": visit_id, "nacin_prijema": nacin_prijema},
        )
    return result


async def mock_update_visit(
    visit_id: str,
    reason: str | None = None,
    *,
    patient_mbo: str = "",
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    result = {"mock": True, "success": True, "visit_id": visit_id, "status": "in-progress"}
    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action="visit_update",
            details={"visit_id": visit_id, "mbo": patient_mbo},
        )
    return result


async def mock_visit_action(
    visit_id: str,
    action: str,
    *,
    patient_mbo: str = "",
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> dict:
    status_map = {"close": "finished", "reopen": "in-progress", "storno": "entered-in-error"}
    new_status = status_map.get(action, "in-progress")
    result = {"mock": True, "success": True, "visit_id": visit_id, "status": new_status}
    if db and user_id and tenant_id:
        await _write_audit(
            db, tenant_id, user_id,
            action=f"visit_{action}",
            details={"visit_id": visit_id, "action": action, "mbo": patient_mbo},
        )
    return result


async def mock_list_visits(
    patient_mbo: str,
    db: AsyncSession | None = None,
    user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> list[dict]:
    if db and user_id and tenant_id:
        await _write_audit(db, tenant_id, user_id, action="visit_list", details={"mbo": patient_mbo})
    return [{"mock": True, **v} for v in _MOCK_VISITS]


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
     "izdavatelj": "HM DIGITAL ordinacija", "svrha": "Kardiološki nalaz",
     "specijalist": "Dr. TESTNI55", "status": "Otvorena", "type": "specijalisticki_nalaz",
     "patient_mbo": "999990260"},
    {"id": "DOC-002", "datum_izdavanja": "2026-03-20",
     "izdavatelj": "HM DIGITAL ordinacija", "svrha": "RTG snimka — ambulantno izvješće",
     "specijalist": "Dr. TESTNI55", "status": "Otvorena", "type": "ambulantno_izvjesce",
     "patient_mbo": "999990260"},
    {"id": "DOC-003", "datum_izdavanja": "2026-03-15",
     "izdavatelj": "HM DIGITAL ordinacija", "svrha": "Laboratorijski nalaz",
     "specijalist": "Dr. TESTNI55", "status": "Zatvorena", "type": "nalaz",
     "patient_mbo": "999990260"},
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
    now = datetime.now(UTC)
    result = {
        "mock": True, "success": True,
        "new_reference_id": new_ref, "replaced_reference_id": original_reference_id,
        "signature_data": base64.b64encode(f"mock-signature-replace-{new_ref}".encode()).decode(),
        "signed_at": now.isoformat(),
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
