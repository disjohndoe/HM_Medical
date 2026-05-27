import json  # noqa: F401
import logging
from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import status as http_status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CEZIH_ELIGIBLE_TYPES, CEZIH_MANDATORY_TYPES
from app.core.plan_enforcement import check_cezih_access, check_hzzo_access
from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models.audit_log import AuditLog
from app.models.medical_record import MedicalRecord
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.cezih import (
    CaseActionResponse,
    CaseItem,
    CaseResponse,
    CasesListResponse,
    CezihActivityItem,
    CezihActivityListResponse,
    CezihDashboardStats,
    CezihImportByIdentifierRequest,
    CezihImportRequest,
    CezihStatusResponse,
    CodeSystemItem,
    CreateCaseRequest,
    CreateVisitRequest,
    DocumentActionResponse,
    DocumentSearchItem,
    ENalazRequest,
    ENalazResponse,
    EReceptRequest,
    EReceptResponse,
    EReceptStornoResponse,
    ForeignerRegistrationRequest,
    ForeignerRegistrationResponse,
    InsuranceCheckRequest,
    InsuranceCheckResponse,
    LijekItem,
    OidGenerateRequest,
    OidGenerateResponse,
    OrganizationItem,
    PatientCezihENalaz,
    PatientCezihERecept,
    PatientCezihInsurance,
    PatientCezihSummary,
    PatientIdentifierSearchResponse,
    PractitionerItem,
    ReplaceDocumentRequest,
    ReplaceDocumentWithEditRequest,
    UpdateCaseDataRequest,
    UpdateCaseStatusRequest,
    UpdateVisitRequest,
    ValueSetExpandResponse,
    VisitActionRequest,
    VisitResponse,
    VisitsListResponse,
)
from app.services.card_verification import get_card_status
from app.services.cezih import dispatcher as cezih

router = APIRouter(prefix="/cezih", tags=["cezih"])

logger = logging.getLogger(__name__)


def _http_client(request: Request):
    return request.app.state.http_client


async def _get_tenant_cezih_config(
    db: AsyncSession,
    tenant_id,
) -> tuple[str, str, str]:
    """Get validated org_code, OID, and naziv for a tenant. Raises HTTPException if missing."""
    from fastapi import HTTPException

    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Zakupac nije pronađen.")
    if not tenant.sifra_ustanove:
        raise HTTPException(
            status_code=422,
            detail="Šifra zdravstvene ustanove nije konfigurirana. Postavite je u Postavke > Organizacija.",
        )
    if not tenant.oid:
        raise HTTPException(
            status_code=422,
            detail="OID informacijskog sustava nije generiran. Kliknite 'Generiraj OID' u Postavke > Klinika.",
        )
    return tenant.sifra_ustanove, tenant.oid, tenant.naziv


@router.get("/status", response_model=CezihStatusResponse)
async def get_cezih_status(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await cezih.cezih_status(current_user.tenant_id, http_client=_http_client(request))

    # Always fetch card/VPN status for 3-indicator browser display
    card_info = get_card_status(current_user.tenant_id, current_user.card_holder_name)
    # If user has card_holder_name configured, require exact match (multi-doctor).
    # Otherwise fall back to any card inserted in any agent (single-doctor / unconfigured).
    if current_user.card_holder_name:
        card_detected = card_info.get("my_card_inserted", False)
    else:
        card_detected = card_info.get("card_inserted", False)
    result["card_inserted"] = card_detected
    result["vpn_connected"] = card_info.get("vpn_connected", False)
    result["reader_available"] = card_info.get("reader_available", False)
    result["card_holder"] = card_info.get("card_holder") if card_detected else None

    # Only show doctor/clinic identity when agent is connected AND card is inserted
    if result.get("agent_connected") and card_detected:
        tenant = await db.get(Tenant, current_user.tenant_id)
        titula = current_user.titula or ""
        doctor_name = f"{titula} {current_user.ime} {current_user.prezime}".strip()
        result["connected_doctor"] = doctor_name
        result["connected_clinic"] = tenant.naziv if tenant else None
    else:
        result["connected_doctor"] = None
        result["connected_clinic"] = None

    return result


@router.post("/import-patient")
async def import_patient_from_cezih(
    request: Request,
    data: CezihImportRequest,
    current_user: User = Depends(require_roles("admin", "doctor", "nurse")),
    db: AsyncSession = Depends(get_db),
):
    """Fetch patient from CEZIH by MBO and create in local database."""
    await check_cezih_access(db, current_user.tenant_id)
    return await cezih.import_patient_from_cezih(
        data.mbo,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )


@router.post("/import-patient-by-identifier")
async def import_patient_by_identifier(
    request: Request,
    data: CezihImportByIdentifierRequest,
    current_user: User = Depends(require_roles("admin", "doctor", "nurse")),
    db: AsyncSession = Depends(get_db),
):
    """Fetch patient from CEZIH by MBO/EHIC/passport and create in local database.

    Unlike /import-patient (MBO-only), this supports foreigners too — their
    passport/EHIC/CEZIH-ID are persisted into the corresponding columns.
    """
    await check_cezih_access(db, current_user.tenant_id)
    return await cezih.import_patient_by_identifier(
        data.identifier_type,
        data.identifier_value,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )


@router.post("/provjera-osiguranja", response_model=InsuranceCheckResponse)
async def provjera_osiguranja(
    request: Request,
    data: InsuranceCheckRequest,
    current_user: User = Depends(require_roles("admin", "doctor", "nurse")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    if data.patient_id is not None:
        return await cezih.insurance_check(
            data.patient_id,
            db=db,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            http_client=_http_client(request),
        )
    if data.identifier_type and data.identifier_value:
        return await cezih.insurance_check_by_identifier(
            data.identifier_type,
            data.identifier_value,
            db=db,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            http_client=_http_client(request),
        )
    if data.mbo:
        return await cezih.insurance_check_by_mbo(
            data.mbo,
            db=db,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            http_client=_http_client(request),
        )
    raise HTTPException(
        status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Potrebno je proslijediti patient_id ili mbo",
    )


@router.post("/e-nalaz", response_model=ENalazResponse)
async def send_enalaz(
    request: Request,
    data: ENalazRequest,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid, org_name = await _get_tenant_cezih_config(db, current_user.tenant_id)
    practitioner_name = f"{current_user.ime} {current_user.prezime}".strip()

    return await cezih.send_enalaz(
        db,
        current_user.tenant_id,
        data.patient_id,
        data.record_id,
        user_id=current_user.id,
        http_client=_http_client(request),
        practitioner_id=current_user.practitioner_id or "",
        org_code=org_code,
        source_oid=source_oid,
        encounter_id=data.encounter_id,
        case_id=data.case_id,
        practitioner_name=practitioner_name,
        org_name=org_name,
    )


@router.post("/e-recept", response_model=EReceptResponse)
async def send_erecept(
    request: Request,
    data: EReceptRequest,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    await check_hzzo_access(db, current_user.tenant_id)
    lijekovi_dicts = [item.model_dump() for item in data.lijekovi]
    return await cezih.send_erecept(
        data.patient_id,
        lijekovi_dicts,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )


@router.delete("/e-recept/{recept_id}", response_model=EReceptStornoResponse)
async def cancel_erecept(
    request: Request,
    recept_id: str,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    await check_hzzo_access(db, current_user.tenant_id)
    return await cezih.cancel_erecept(
        recept_id,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )


# --- Feature 1: Activity Log ---


@router.get("/activity", response_model=CezihActivityListResponse)
async def get_cezih_activity(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    base = select(AuditLog).where(
        AuditLog.tenant_id == current_user.tenant_id,
        AuditLog.resource_type == "cezih",
    )

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar() or 0

    result = await db.execute(base.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit))
    rows = result.scalars().all()

    items = [
        CezihActivityItem(
            id=str(r.id),
            action=r.action,
            resource_id=str(r.resource_id) if r.resource_id else None,
            details=r.details,
            created_at=r.created_at,
            user_id=str(r.user_id) if r.user_id else None,
        )
        for r in rows
    ]

    return CezihActivityListResponse(items=items, total=total)


# --- Feature 2: Patient CEZIH Summary ---


@router.get("/patient/{patient_id}/summary", response_model=PatientCezihSummary)
async def get_patient_cezih_summary(
    patient_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # e-Nalaz table: all CEZIH-eligible medical records for this patient
    # (sent + unsent). Status is derived on the frontend from cezih_sent_at / cezih_storno.
    records_result = await db.execute(
        select(
            MedicalRecord,
            User.ime.label("doktor_ime"),
            User.prezime.label("doktor_prezime"),
        )
        .outerjoin(User, MedicalRecord.doktor_id == User.id)
        .where(
            MedicalRecord.tenant_id == current_user.tenant_id,
            MedicalRecord.patient_id == patient_id,
            MedicalRecord.tip.in_(CEZIH_ELIGIBLE_TYPES),
        )
        .order_by(func.coalesce(MedicalRecord.cezih_sent_at, MedicalRecord.created_at).desc())
    )
    records = records_result.all()

    e_nalaz_history = [
        PatientCezihENalaz(
            record_id=str(row[0].id),
            datum=row[0].created_at,
            tip=row[0].tip,
            dijagnoza_mkb=row[0].dijagnoza_mkb,
            dijagnoza_tekst=row[0].dijagnoza_tekst,
            doktor_ime=row.doktor_ime,
            doktor_prezime=row.doktor_prezime,
            sensitivity=row[0].sensitivity,
            reference_id=row[0].cezih_reference_id,
            document_oid=row[0].cezih_document_oid,
            cezih_sent_at=row[0].cezih_sent_at,
            cezih_storno=row[0].cezih_storno,
            cezih_signed=bool(row[0].cezih_signature_data),
            cezih_signed_at=row[0].cezih_signed_at,
            cezih_last_replaced_at=row[0].cezih_last_replaced_at,
            updated_at=row[0].updated_at,
            cezih_last_error_code=row[0].cezih_last_error_code,
            cezih_last_error_display=row[0].cezih_last_error_display,
            cezih_last_error_diagnostics=row[0].cezih_last_error_diagnostics,
        )
        for row in records
    ]

    # e-Recept history from audit log
    recept_result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.tenant_id == current_user.tenant_id,
            AuditLog.resource_type == "cezih",
            AuditLog.action == "e_recept_send",
            AuditLog.resource_id == patient_id,
        )
        .order_by(AuditLog.created_at.desc())
    )
    recept_logs = recept_result.scalars().all()

    e_recept_history = []
    for log in recept_logs:
        details = json.loads(log.details) if log.details else {}
        e_recept_history.append(
            PatientCezihERecept(
                recept_id=details.get("recept_id", "—"),
                datum=log.created_at,
                lijekovi=details.get("lijekovi", []),
            )
        )

    # Insurance: read from patient record (persisted on each insurance check)
    from app.models.patient import Patient
    from app.services.cezih.service import (
        _IDENTIFIER_LABEL_MAP,
        resolve_cezih_identifier,
    )

    patient = await db.get(Patient, patient_id)
    insurance = PatientCezihInsurance()
    if patient and patient.cezih_insurance_status:
        insurance = PatientCezihInsurance(
            mbo=patient.mbo,
            status_osiguranja=patient.cezih_insurance_status,
            last_checked=patient.cezih_insurance_checked_at,
        )

    identifier_label: str | None = None
    if patient:
        try:
            system_uri, _ = resolve_cezih_identifier(patient)
            identifier_label = _IDENTIFIER_LABEL_MAP.get(system_uri)
        except Exception:
            identifier_label = None

    return PatientCezihSummary(
        insurance=insurance,
        e_nalaz_history=e_nalaz_history,
        e_recept_history=e_recept_history,
        identifier_label=identifier_label,
    )


# --- Feature 3: Dashboard Stats ---


@router.get("/dashboard-stats", response_model=CezihDashboardStats)
async def get_cezih_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    # Today's CEZIH operations count
    count_result = await db.execute(
        select(func.count()).where(
            AuditLog.tenant_id == current_user.tenant_id,
            AuditLog.resource_type == "cezih",
            AuditLog.created_at >= today_start,
        )
    )
    danas = count_result.scalar() or 0

    # Most recent CEZIH operation
    last_result = await db.execute(
        select(AuditLog.created_at)
        .where(
            AuditLog.tenant_id == current_user.tenant_id,
            AuditLog.resource_type == "cezih",
        )
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    last_op = last_result.scalar_one_or_none()

    # Unsent mandatory CEZIH nalazi count
    unsent_result = await db.execute(
        select(func.count()).where(
            MedicalRecord.tenant_id == current_user.tenant_id,
            MedicalRecord.tip.in_(CEZIH_MANDATORY_TYPES),
            MedicalRecord.cezih_sent == False,  # noqa: E712
            MedicalRecord.cezih_storno == False,  # noqa: E712
        )
    )
    unsent_count = unsent_result.scalar() or 0

    return CezihDashboardStats(
        danas_operacije=danas,
        neposlani_nalazi=unsent_count,
        zadnja_operacija=last_op,
    )


# --- Feature 4: Drug Search ---


@router.get("/lijekovi", response_model=list[LijekItem])
async def search_drugs(
    q: str = Query("", min_length=0),
    current_user: User = Depends(get_current_user),
):
    return await cezih.drug_search(q)


@router.post("/lijekovi/sync")
async def trigger_drug_sync(
    current_user: User = Depends(require_roles("admin")),
):
    """Manually trigger HZZO drug list sync (admin only)."""
    from app.services.halmed_sync_service import sync_hzzo_drugs

    result = await sync_hzzo_drugs()
    return result


# ============================================================
# TC6: OID Registry Lookup
# ============================================================


@router.post("/oid-generate", response_model=OidGenerateResponse)
async def oid_generate(
    request: Request,
    data: OidGenerateRequest,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    return await cezih.oid_generate(
        data.quantity,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )


# ============================================================
# TC7: Code System Query
# ============================================================


@router.get("/code-system", response_model=list[CodeSystemItem])
async def query_code_system(
    request: Request,
    system: str = Query(..., description="Code system name: icd10-hr, nacin-prijema, lijekovi"),
    q: str = Query("", description="Search query"),
    count: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await cezih.code_system_query(
        system,
        q,
        count,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )


@router.get("/icd10/search", response_model=list[CodeSystemItem])
async def search_icd10_local(
    q: str = Query("", description="Search query (code or name, min 1 char)"),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """Search local ICD-10 codes (synced from CEZIH, no VPN needed)."""
    from app.services.icd10_sync_service import search_icd10

    return await search_icd10(q, limit)


@router.get("/dts/search", response_model=list[CodeSystemItem])
async def search_dts_local(
    q: str = Query("", description="Search query (DTS code or name, min 1 char)"),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """Search local DTS procedure codes (synced from CEZIH, no VPN needed)."""
    from app.services.dts_sync_service import search_dts

    return await search_dts(q, limit)


# ============================================================
# TC8: Value Set Expand
# ============================================================


@router.get("/value-set", response_model=ValueSetExpandResponse)
async def expand_value_set(
    request: Request,
    url: str = Query(..., description="ValueSet canonical URL"),
    filter: str = Query(None, description="Filter text"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await cezih.value_set_expand(
        url,
        filter,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )


# ============================================================
# TC9: Subject Registry (mCSD)
# ============================================================


@router.get("/organizations", response_model=list[OrganizationItem])
async def search_organizations(
    request: Request,
    name: str = Query(..., min_length=2),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await cezih.organization_search(
        name,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )


@router.get("/practitioners", response_model=list[PractitionerItem])
async def search_practitioners(
    request: Request,
    name: str = Query(..., min_length=2),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await cezih.practitioner_search(
        name,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )


# ============================================================
# Foreigner patient search by passport / EHIC (PDQm ITI-78)
# ============================================================


@router.get("/patients/search", response_model=PatientIdentifierSearchResponse)
async def search_patient_by_identifier(
    request: Request,
    system: str = Query(..., description="Tip identifikatora: mbo, putovnica, ili ehic"),
    value: str = Query(..., description="Vrijednost identifikatora"),
    current_user: User = Depends(require_roles("admin", "doctor", "nurse")),
    db: AsyncSession = Depends(get_db),
):
    """Search CEZIH patient registry by MBO, passport, or EHIC number."""
    from fastapi import HTTPException
    from fastapi import status as http_status

    from app.services.cezih.exceptions import CezihAuthError, CezihError
    from app.services.cezih.service import search_patient_by_identifier as _search

    await check_cezih_access(db, current_user.tenant_id)
    try:
        result = await _search(
            _http_client(request),
            identifier_system=system,
            value=value,
            tenant_id=current_user.tenant_id,
        )
    except CezihAuthError as e:
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
    except CezihError as e:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message) from e

    # Enrich with local_patient_id so the UI can choose "Otvori karton" vs
    # "Dodaj u kartoteku". Match on any of the CEZIH-returned identifiers —
    # the same patient can be stored under a different column locally.
    from sqlalchemy import or_

    from app.models.patient import Patient
    from app.services.cezih.builders.common import (
        ID_EHIC,
        ID_JEDINSTVENI,
        ID_MBO,
        ID_OIB,
        ID_PUTOVNICA,
    )

    filters = []
    for ident in result.get("identifikatori") or []:
        sys_uri = ident.get("system")
        val = ident.get("value")
        if not sys_uri or not val:
            continue
        if sys_uri == ID_MBO:
            filters.append(Patient.mbo == val)
        elif sys_uri == ID_OIB:
            filters.append(Patient.oib == val)
        elif sys_uri == ID_PUTOVNICA:
            filters.append(Patient.broj_putovnice == val)
        elif sys_uri == ID_EHIC:
            filters.append(Patient.ehic_broj == val)
        elif sys_uri == ID_JEDINSTVENI:
            filters.append(Patient.cezih_patient_id == val)
    if result.get("cezih_id"):
        filters.append(Patient.cezih_patient_id == result["cezih_id"])

    if filters:
        lookup = await db.execute(
            select(Patient.id)
            .where(
                Patient.tenant_id == current_user.tenant_id,
                Patient.is_active.is_(True),
                or_(*filters),
            )
            .limit(1),
        )
        local_id = lookup.scalar_one_or_none()
        if local_id:
            result["local_patient_id"] = str(local_id)

    return result


# ============================================================
# TC11: Foreigner Registration (PMIR)
# ============================================================


@router.post("/patients/foreigner", response_model=ForeignerRegistrationResponse)
async def register_foreigner(
    request: Request,
    data: ForeignerRegistrationRequest,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    from app.models.patient import Patient

    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid, _ = await _get_tenant_cezih_config(db, current_user.tenant_id)
    result = await cezih.foreigner_registration(
        data.model_dump(),
        org_code=org_code,
        source_oid=source_oid,
        practitioner_id=current_user.practitioner_id or "",
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )

    if result.get("success"):
        spol_map = {"male": "M", "female": "Z"}
        dob = date.fromisoformat(data.datum_rodjenja) if data.datum_rodjenja else None
        # PMIR returns CEZIH's jedinstveni-identifikator-pacijenta in the "mbo" key.
        # Foreigners don't have a Croatian MBO — leave patients.mbo NULL.
        # Strict-shape guard: only persist if the value is all-digits. HZZO Provjera
        # Spremnosti rejected 2026-05-11 over a CUID stored in this column.
        raw_cezih_id = result.get("mbo") or ""
        cezih_id = raw_cezih_id if raw_cezih_id.isdigit() else None
        if raw_cezih_id and not cezih_id:
            logger.warning(
                "Foreigner registration returned non-numeric CEZIH ID %r — not persisting. "
                "Patient row created without cezih_patient_id; re-run TC11 to obtain valid JID.",
                raw_cezih_id,
            )
        patient = Patient(
            tenant_id=current_user.tenant_id,
            ime=data.ime,
            prezime=data.prezime,
            datum_rodjenja=dob,
            spol=spol_map.get(data.spol),
            mbo=None,
            cezih_patient_id=cezih_id,
            broj_putovnice=data.broj_putovnice or None,
            ehic_broj=data.ehic_broj or None,
            drzavljanstvo=data.drzavljanstvo or None,
        )
        db.add(patient)
        await db.flush()
        await db.refresh(patient)
        result["local_patient_id"] = str(patient.id)

    return result


# ============================================================
# TC15-17: Case Management
# ============================================================


@router.get("/cases", response_model=CasesListResponse)
async def list_cases(
    request: Request,
    patient_id: UUID = Query(..., description="Local patient UUID"),
    current_user: User = Depends(require_roles("admin", "doctor", "nurse")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    cases = await cezih.dispatch_retrieve_cases(
        patient_id,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )
    return CasesListResponse(cases=[CaseItem.model_validate(c) for c in cases])


@router.post("/cases", response_model=CaseResponse)
async def create_case(
    request: Request,
    data: CreateCaseRequest,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid, _ = await _get_tenant_cezih_config(db, current_user.tenant_id)
    return await cezih.dispatch_create_case(
        data.patient_id,
        current_user.practitioner_id or "",
        org_code,
        data.icd_code,
        data.icd_display,
        data.onset_date,
        data.verification_status,
        data.note,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
        source_oid=source_oid,
    )


@router.put("/cases/{case_id}/status", response_model=CaseActionResponse)
async def update_case_status(
    request: Request,
    case_id: str,
    data: UpdateCaseStatusRequest,
    patient_id: UUID = Query(..., description="Local patient UUID"),
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid, _ = await _get_tenant_cezih_config(db, current_user.tenant_id)
    return await cezih.dispatch_update_case(
        case_id,
        patient_id,
        current_user.practitioner_id or "",
        org_code,
        data.action,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
        source_oid=source_oid,
    )


@router.put("/cases/{case_id}/data", response_model=CaseActionResponse)
async def update_case_data(
    request: Request,
    case_id: str,
    data: UpdateCaseDataRequest,
    patient_id: UUID = Query(..., description="Local patient UUID"),
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid, _ = await _get_tenant_cezih_config(db, current_user.tenant_id)
    return await cezih.dispatch_update_case_data(
        case_id,
        patient_id,
        current_user.practitioner_id or "",
        org_code,
        current_clinical_status=data.current_clinical_status,
        verification_status=data.verification_status,
        icd_code=data.icd_code,
        icd_display=data.icd_display,
        onset_date=data.onset_date,
        abatement_date=data.abatement_date,
        note_text=data.note,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
        source_oid=source_oid,
    )


# ============================================================
# TC19-22: Document Operations
# ============================================================


@router.get("/documents", response_model=list[DocumentSearchItem])
async def search_documents(
    request: Request,
    patient_id: UUID | None = Query(None, description="Local patient UUID"),
    type: str = Query(None, description="Document type (nalaz, uputnica)"),
    date_from: str = Query(None, description="Date from (YYYY-MM-DD)"),
    date_to: str = Query(None, description="Date to (YYYY-MM-DD)"),
    status: str = Query(None, description="FHIR status (current, superseded, entered-in-error)"),
    current_user: User = Depends(require_roles("admin", "doctor", "nurse")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    return await cezih.dispatch_search_documents(
        patient_id=patient_id,
        document_type=type,
        date_from=date_from,
        date_to=date_to,
        status_filter=status,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )


@router.put("/e-nalaz/{reference_id}", response_model=DocumentActionResponse)
async def replace_document(
    request: Request,
    reference_id: str,
    data: ReplaceDocumentRequest | None = None,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid, org_name = await _get_tenant_cezih_config(db, current_user.tenant_id)
    practitioner_name = f"{current_user.ime} {current_user.prezime}".strip() if hasattr(current_user, "ime") else ""
    return await cezih.dispatch_replace_document(
        reference_id,
        record_id=data.record_id if data else None,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
        org_code=org_code,
        practitioner_id=current_user.practitioner_id,
        practitioner_name=practitioner_name,
        encounter_id=data.encounter_id if data else "",
        case_id=data.case_id if data else "",
        org_name=org_name,
    )


@router.put("/e-nalaz/{reference_id}/replace-with-edit", response_model=DocumentActionResponse)
async def replace_document_with_edit(
    request: Request,
    reference_id: str,
    data: ReplaceDocumentWithEditRequest,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    """Atomic edit + CEZIH replace. Replaces the old two-step flow where the
    frontend PATCHed /medical-records first and then called CEZIH replace —
    if CEZIH failed the local record was already edited, so this endpoint
    gates the local edit on CEZIH 2xx."""
    await check_cezih_access(db, current_user.tenant_id)
    org_code, _, org_name = await _get_tenant_cezih_config(db, current_user.tenant_id)
    practitioner_name = f"{current_user.ime} {current_user.prezime}".strip() if hasattr(current_user, "ime") else ""
    edits = data.model_dump(exclude={"record_id", "patient_id", "encounter_id", "case_id"}, exclude_none=False)
    return await cezih.dispatch_replace_document_with_edit(
        reference_id,
        record_id=data.record_id,
        patient_id=data.patient_id,
        edits=edits,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
        org_code=org_code,
        practitioner_id=current_user.practitioner_id,
        practitioner_name=practitioner_name,
        encounter_id=data.encounter_id,
        case_id=data.case_id,
        org_name=org_name,
    )


@router.put("/e-nalaz/{reference_id}/amend-with-edit", response_model=DocumentActionResponse)
async def amend_document_with_edit(
    request: Request,
    reference_id: str,
    data: ReplaceDocumentWithEditRequest,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    """Doctor-facing edit via the "entered-in-error line" — submit a new
    DocumentReference (relatesTo.code=appends) then cancel the old one
    (entered-in-error). Unlike replace-with-edit (which sets the old doc to
    `superseded` and permanently blocks visit storno — ERR_ENCOUNTER_2001 ↔
    ERR_DOM_10035), this leaves no `superseded` document, so the visit stays
    stornable. replace-with-edit is kept available for TC19/replace scenarios."""
    await check_cezih_access(db, current_user.tenant_id)
    org_code, _, org_name = await _get_tenant_cezih_config(db, current_user.tenant_id)
    practitioner_name = f"{current_user.ime} {current_user.prezime}".strip() if hasattr(current_user, "ime") else ""
    edits = data.model_dump(exclude={"record_id", "patient_id", "encounter_id", "case_id"}, exclude_none=False)
    return await cezih.dispatch_edit_document_via_amend(
        reference_id,
        record_id=data.record_id,
        patient_id=data.patient_id,
        edits=edits,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
        org_code=org_code,
        practitioner_id=current_user.practitioner_id,
        practitioner_name=practitioner_name,
        encounter_id=data.encounter_id,
        case_id=data.case_id,
        org_name=org_name,
    )


@router.delete("/e-nalaz/{reference_id}", response_model=DocumentActionResponse)
async def cancel_document(
    request: Request,
    reference_id: str,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    # Storno = the 2-entry HRCancelDocumentBundle (status=entered-in-error) - the
    # only path that actually flips the doc to stornoed on CEZIH. The legacy
    # replace-style cancel was removed: it created a successor with
    # status=current, left the original active on CEZIH despite our mirror
    # marking cezih_storno=true, and that silent divergence triggered
    # ERR_ENCOUNTER_2001 on later visit storno.
    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid, org_name = await _get_tenant_cezih_config(db, current_user.tenant_id)
    practitioner_name = f"{current_user.ime} {current_user.prezime}".strip() if hasattr(current_user, "ime") else ""
    return await cezih.dispatch_cancel_document_canonical(
        reference_id,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
        org_code=org_code,
        practitioner_id=current_user.practitioner_id,
        practitioner_name=practitioner_name,
        org_name=org_name,
    )


@router.get("/e-nalaz/{reference_id}/document")
async def retrieve_document(
    request: Request,
    reference_id: str,
    url: str = Query(None, description="CEZIH content URL from DocumentReference"),
    oid: str = Query(None, description="Document OID — constructs ITI-68 URL"),
    current_user: User = Depends(require_roles("admin", "doctor", "nurse")),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response

    # Construct content_url from OID when direct URL not provided
    if not url and oid:
        import base64

        data_plain = f"documentUniqueId=urn:ietf:rfc:3986|urn:oid:{oid}&position=0"
        data_b64 = base64.b64encode(data_plain.encode()).decode()
        from app.config import settings

        base = settings.CEZIH_FHIR_BASE_URL.rstrip("/")
        url = f"{base}/services-router/gateway/doc-mhd-svc/api/v1/iti-68-service?data={data_b64}"

    await check_cezih_access(db, current_user.tenant_id)
    content = await cezih.dispatch_retrieve_document(
        reference_id,
        document_url=url,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )
    original_size = len(content)
    is_pdf = content.startswith(b"%PDF")

    if not is_pdf:
        # CEZIH returned non-PDF content — likely an error or empty response
        text_preview = content.decode("utf-8", errors="replace")[:500]
        logger.warning(
            "CEZIH document %s: NOT PDF (%d bytes), wrapping as PDF. Content preview: %r",
            reference_id,
            original_size,
            text_preview,
        )
        from app.services.pdf_generator import cezih_text_to_pdf

        text = content.decode("utf-8", errors="replace")
        content = cezih_text_to_pdf(text)
        logger.info("Wrapped non-PDF response as PDF: %d -> %d bytes", original_size, len(content))
    else:
        logger.info("CEZIH document %s: valid PDF (%d bytes)", reference_id, original_size)

    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=cezih-{reference_id}.pdf"},
    )


# ============================================================
# TC12-14: Visit Management
# ============================================================


@router.get("/visits", response_model=VisitsListResponse)
async def list_visits(
    request: Request,
    patient_id: UUID = Query(...),
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    visits = await cezih.dispatch_list_visits(
        patient_id,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )
    return VisitsListResponse(visits=visits)  # type: ignore[arg-type]


@router.post("/visits", response_model=VisitResponse)
async def create_visit(
    request: Request,
    data: CreateVisitRequest,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid, _ = await _get_tenant_cezih_config(db, current_user.tenant_id)
    return await cezih.dispatch_create_visit(
        data.patient_id,
        data.nacin_prijema,
        data.vrsta_posjete,
        data.tip_posjete,
        data.reason,
        data.case_id,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
        practitioner_id=current_user.practitioner_id or "",
        org_code=org_code,
        source_oid=source_oid,
    )


@router.patch("/visits/{visit_id}", response_model=VisitResponse)
async def update_visit(
    request: Request,
    visit_id: str,
    data: UpdateVisitRequest,
    patient_id: UUID = Query(..., description="Local patient UUID"),
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid, _ = await _get_tenant_cezih_config(db, current_user.tenant_id)
    return await cezih.dispatch_update_visit(
        visit_id,
        patient_id,
        data.reason,
        nacin_prijema=data.nacin_prijema,
        vrsta_posjete=data.vrsta_posjete,
        tip_posjete=data.tip_posjete,
        diagnosis_case_id=data.diagnosis_case_id,
        additional_practitioner_id=data.additional_practitioner_id,
        period_start=data.period_start,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
        practitioner_id=current_user.practitioner_id or "",
        org_code=org_code,
        source_oid=source_oid,
    )


@router.post("/visits/{visit_id}/action", response_model=VisitResponse)
async def visit_action(
    request: Request,
    visit_id: str,
    data: VisitActionRequest,
    patient_id: UUID = Query(..., description="Local patient UUID"),
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid, org_name = await _get_tenant_cezih_config(db, current_user.tenant_id)
    practitioner_name = f"{current_user.ime} {current_user.prezime}".strip() if hasattr(current_user, "ime") else ""
    return await cezih.dispatch_visit_action(
        visit_id,
        data.action,
        patient_id,
        period_start=data.period_start,
        db=db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
        practitioner_id=current_user.practitioner_id or "",
        practitioner_name=practitioner_name,
        org_code=org_code,
        org_name=org_name,
        source_oid=source_oid,
        confirm_cascade_docs=data.confirm_cascade_docs,
    )


# ---------------------------------------------------------------------------
# TEMP DIAGNOSTIC — TC20 storno "does cancelling the head unblock Encounter 1.4?"
# Runs the REAL storno cascade + 1.4 with both silent-suppression branches
# BYPASSED, so the true CEZIH outcome (ERR_ENCOUNTER_2001 vs success) surfaces.
# Returns raw JSON incl. any CEZIH error. Admin-only. REMOVE after the test.
# ---------------------------------------------------------------------------
@router.post("/visits/{visit_id}/action-diag")
async def visit_action_diag(
    request: Request,
    visit_id: str,
    patient_id: UUID = Query(..., description="Local patient UUID"),
    action: str = Query("storno"),
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import JSONResponse

    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid, org_name = await _get_tenant_cezih_config(db, current_user.tenant_id)
    practitioner_name = (
        f"{current_user.ime} {current_user.prezime}".strip() if hasattr(current_user, "ime") else ""
    )
    try:
        result = await cezih.dispatch_visit_action(
            visit_id,
            action,
            patient_id,
            db=db,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            http_client=_http_client(request),
            practitioner_id=current_user.practitioner_id or "",
            practitioner_name=practitioner_name,
            org_code=org_code,
            org_name=org_name,
            source_oid=source_oid,
            confirm_cascade_docs=True,
            _diag_no_suppress=True,
        )
        return JSONResponse({"ok": True, "result": result})
    except HTTPException as e:
        return JSONResponse(
            status_code=200,
            content={"ok": False, "error_type": "HTTPException", "status": e.status_code, "detail": e.detail},
        )
    except Exception as e:  # noqa: BLE001 - diagnostic: surface everything
        return JSONResponse(
            status_code=200,
            content={"ok": False, "error_type": type(e).__name__, "detail": str(e)},
        )


# TEMP DIAGNOSTIC — cancel an EXACT DocumentReference version (e.g. a superseded
# predecessor named in ERR_ENCOUNTER_2001 as DocumentReference/{id}/_history/{ver}).
# Bypasses head-collapse: vread the exact version to get its OID, build the
# HRCancelDocumentBundle for THAT OID, POST it, and return CEZIH's raw response.
# Decides fixable (cancel succeeds) vs hard-limit (ERR_DOM_10035). REMOVE after test.
@router.post("/_diag/cancel-docver")
async def diag_cancel_docver(
    request: Request,
    patient_id: UUID = Query(...),
    reference_id: str = Query(...),
    version_id: str = Query(...),
    tip: str = Query("specijalisticki_nalaz"),
    encounter_id: str = Query(""),
    case_id: str = Query(""),
    dry_run: bool = Query(False),
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import JSONResponse

    from app.models.patient import Patient
    from app.services.cezih import service as real_service
    from app.services.cezih.client import CezihFhirClient
    from app.services.cezih.dispatchers.common import _require_audit_params
    from app.services.cezih.dispatchers.documents import _resolve_djelatnost
    from app.services.cezih.fhir_api.documents import _extract_oid_from_docref, build_cancel_bundle

    # Sets current_tenant_id/user_id/db contextvars so CezihFhirClient routes
    # through the agent (server has no VPN) and resolves signing method.
    _require_audit_params(db, current_user.id, current_user.tenant_id)
    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid, org_name = await _get_tenant_cezih_config(db, current_user.tenant_id)
    patient = await db.get(Patient, patient_id)
    id_sys, id_val = real_service.resolve_cezih_identifier(patient)
    patient_data = {
        "mbo": id_val, "identifier_system": id_sys, "identifier_value": id_val,
        "ime": patient.ime, "prezime": patient.prezime,
    }
    djelatnost_code, djelatnost_display = await _resolve_djelatnost(db, current_user.tenant_id, current_user.id)
    fhir = CezihFhirClient(_http_client(request), tenant_id=current_user.tenant_id)
    trace: dict = {"reference_id": reference_id, "version_id": version_id}
    try:
        # vread (DocumentReference/{id}/_history/{ver}) 404s on this gateway, so
        # resolve the OID from the patient-scoped ITI-67 search (proven to return
        # superseded predecessors) by matching the FHIR id.
        search = await fhir.get(
            "doc-mhd-svc/api/v1/DocumentReference",
            params={
                "patient.identifier": f"{id_sys}|{id_val}",
                "status": "current,superseded",
                "_count": 200,
            },
        )
        match = None
        for entry in (search.get("entry") or []) if isinstance(search, dict) else []:
            res = entry.get("resource") or {}
            if res.get("resourceType") == "DocumentReference" and res.get("id", "") == reference_id:
                match = res
                break
        oid = _extract_oid_from_docref(match) if match else ""
        trace["search_status"] = (match.get("status") if match else None)
        trace["search_oid"] = oid
        if not oid:
            return JSONResponse({"ok": False, "stage": "resolve_oid", "trace": trace,
                                 "matched": bool(match)})
        bundle = build_cancel_bundle(
            patient_data=patient_data,
            record_data={"tip": tip},
            original_document_oid=oid,
            djelatnost_code=djelatnost_code,
            djelatnost_display=djelatnost_display,
            practitioner_id=current_user.practitioner_id or "",
            practitioner_name="",
            org_code=org_code,
            encounter_id=encounter_id,
            case_id=case_id,
            org_name=org_name,
        )
        if dry_run:
            return JSONResponse({"ok": True, "stage": "dry_run", "trace": trace, "bundle": bundle})
        resp = await fhir.post("doc-mhd-svc/api/v1/iti-65-service", json_body=bundle)
        return JSONResponse({"ok": True, "stage": "posted", "trace": trace, "response": resp})
    except HTTPException as e:
        return JSONResponse({"ok": False, "stage": "post", "trace": trace, "status": e.status_code, "detail": e.detail})
    except Exception as e:  # noqa: BLE001 - diagnostic: surface everything
        return JSONResponse({"ok": False, "stage": "post", "trace": trace, "error_type": type(e).__name__, "detail": str(e)})


# TEMP DIAGNOSTIC — dump the live document chain topology (id/status/OID/relatesTo)
# so we can find each blocker's CURRENT head. Read-only. REMOVE after analysis.
@router.get("/_diag/doc-chains")
async def diag_doc_chains(
    request: Request,
    patient_id: UUID = Query(...),
    ids: str = Query("", description="comma-separated ids to focus on (optional)"),
    current_user: User = Depends(require_roles("admin")),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import JSONResponse

    from app.models.patient import Patient
    from app.services.cezih import service as real_service
    from app.services.cezih.client import CezihFhirClient
    from app.services.cezih.dispatchers.common import _require_audit_params
    from app.services.cezih.fhir_api.documents import _extract_oid_from_docref

    _require_audit_params(db, current_user.id, current_user.tenant_id)
    await check_cezih_access(db, current_user.tenant_id)
    patient = await db.get(Patient, patient_id)
    id_sys, id_val = real_service.resolve_cezih_identifier(patient)
    fhir = CezihFhirClient(_http_client(request), tenant_id=current_user.tenant_id)

    def _tail(oid: str) -> str:
        oid = (oid or "").replace("urn:oid:", "")
        return oid.rsplit(".", 1)[-1] if oid else ""

    out: dict = {}
    for st in ["current", "superseded", "entered-in-error"]:
        search = await fhir.get(
            "doc-mhd-svc/api/v1/DocumentReference",
            params={"patient.identifier": f"{id_sys}|{id_val}", "status": st, "_count": 200},
        )
        for entry in (search.get("entry") or []) if isinstance(search, dict) else []:
            res = entry.get("resource") or {}
            if res.get("resourceType") != "DocumentReference":
                continue
            rid = res.get("id", "")
            rels = []
            for rel in res.get("relatesTo", []) or []:
                tgt = rel.get("target") or {}
                ref = tgt.get("reference") or (tgt.get("identifier") or {}).get("value") or ""
                rels.append(f"{rel.get('code')}->{ref}")
            ctx = res.get("context") or {}
            enc = [(e.get("identifier") or {}).get("value") for e in (ctx.get("encounter") or [])]
            out[rid] = {
                "status": res.get("status"),
                "oid_tail": _tail(_extract_oid_from_docref(res)),
                "relatesTo": rels,
                "encounter": enc,
            }
    focus = [i.strip() for i in ids.split(",") if i.strip()]
    result = {k: v for k, v in out.items() if k in focus} if focus else out
    return JSONResponse({"total": len(out), "focus": focus, "docs": result})


@router.get("/extsigner/probe/{transaction_code}")
async def probe_extsigner_transaction(
    transaction_code: str,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    """Probe extsigner API to discover retrieval endpoint for signed documents."""
    await check_cezih_access(db, current_user.tenant_id)
    from app.services.cezih_signing import check_extsigner_transaction

    return await check_extsigner_transaction(transaction_code)
