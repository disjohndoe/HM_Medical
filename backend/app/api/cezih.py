import json  # noqa: F401
from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CEZIH_MANDATORY_TYPES
from app.core.plan_enforcement import check_cezih_access, check_hzzo_access
from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models.audit_log import AuditLog
from app.models.medical_record import MedicalRecord
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.cezih import (
    CaseActionResponse,
    CezihImportRequest,
    CaseItem,
    CaseResponse,
    CasesListResponse,
    CezihActivityItem,
    CezihActivityListResponse,
    CezihDashboardStats,
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
    PatientIdentifierSearchResponse,
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
    PractitionerItem,
    ReplaceDocumentRequest,
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


def _http_client(request: Request):
    return request.app.state.http_client


async def _get_tenant_cezih_config(
    db: AsyncSession, tenant_id,
) -> tuple[str, str]:
    """Get validated org_code and OID for a tenant. Raises HTTPException if missing."""
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
            detail="OID informacijskog sustava nije konfiguriran. Postavite ga u Postavke > Organizacija.",
        )
    return tenant.sifra_ustanove, tenant.oid



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
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
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
    return await cezih.insurance_check(
        data.mbo,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )


@router.post("/e-nalaz", response_model=ENalazResponse)
async def send_enalaz(
    request: Request,
    data: ENalazRequest,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid = await _get_tenant_cezih_config(db, current_user.tenant_id)
    practitioner_name = f"{current_user.ime} {current_user.prezime}".strip()

    return await cezih.send_enalaz(
        db, current_user.tenant_id, data.patient_id, data.record_id,
        user_id=current_user.id,
        http_client=_http_client(request),
        practitioner_id=current_user.practitioner_id or "",
        org_code=org_code, source_oid=source_oid,
        encounter_id=data.encounter_id, case_id=data.case_id,
        practitioner_name=practitioner_name,
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
        data.patient_id, lijekovi_dicts,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
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
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
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

    result = await db.execute(
        base.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)
    )
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
    # e-Nalaz history: medical records sent to CEZIH for this patient
    records_result = await db.execute(
        select(MedicalRecord).where(
            MedicalRecord.tenant_id == current_user.tenant_id,
            MedicalRecord.patient_id == patient_id,
            MedicalRecord.cezih_sent == True,  # noqa: E712
        ).order_by(MedicalRecord.cezih_sent_at.desc())
    )
    records = records_result.scalars().all()

    e_nalaz_history = [
        PatientCezihENalaz(
            record_id=str(r.id),
            datum=r.cezih_sent_at or r.created_at,
            tip=r.tip,
            reference_id=r.cezih_reference_id,
            cezih_sent_at=r.cezih_sent_at,
            cezih_storno=r.cezih_storno,
            cezih_signed=bool(r.cezih_signature_data),
            cezih_signed_at=r.cezih_signed_at,
        )
        for r in records
    ]

    # e-Recept history from audit log
    recept_result = await db.execute(
        select(AuditLog).where(
            AuditLog.tenant_id == current_user.tenant_id,
            AuditLog.resource_type == "cezih",
            AuditLog.action == "e_recept_send",
            AuditLog.resource_id == patient_id,
        ).order_by(AuditLog.created_at.desc())
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

    patient = await db.get(Patient, patient_id)
    insurance = PatientCezihInsurance()
    if patient and patient.cezih_insurance_status:
        insurance = PatientCezihInsurance(
            mbo=patient.mbo,
            status_osiguranja=patient.cezih_insurance_status,
            last_checked=patient.cezih_insurance_checked_at,
        )

    return PatientCezihSummary(
        insurance=insurance,
        e_nalaz_history=e_nalaz_history,
        e_recept_history=e_recept_history,
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
        select(AuditLog.created_at).where(
            AuditLog.tenant_id == current_user.tenant_id,
            AuditLog.resource_type == "cezih",
        ).order_by(AuditLog.created_at.desc()).limit(1)
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
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
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
        system, q, count,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
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
        url, filter,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
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
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
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
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
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
    from app.services.cezih.service import search_patient_by_identifier as _search

    await check_cezih_access(db, current_user.tenant_id)
    result = await _search(
        _http_client(request),
        identifier_system=system,
        value=value,
        tenant_id=current_user.tenant_id,
    )
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
    org_code, source_oid = await _get_tenant_cezih_config(db, current_user.tenant_id)
    result = await cezih.foreigner_registration(
        data.model_dump(),
        org_code=org_code, source_oid=source_oid,
        practitioner_id=current_user.practitioner_id or "",
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )

    if result.get("success"):
        spol_map = {"male": "M", "female": "Z"}
        dob = date.fromisoformat(data.datum_rodjenja) if data.datum_rodjenja else None
        # MBO is varchar(9) — foreigners get a longer unique ID instead.
        # Store MBO only if it fits (9 digits); put CEZIH ID in napomena.
        cezih_id = result.get("mbo", "")
        mbo = cezih_id if len(cezih_id) <= 9 else None
        napomena = f"CEZIH PMIR: {cezih_id}" if cezih_id else "Registriran putem CEZIH PMIR"
        patient = Patient(
            tenant_id=current_user.tenant_id,
            ime=data.ime,
            prezime=data.prezime,
            datum_rodjenja=dob,
            spol=spol_map.get(data.spol),
            mbo=mbo,
            napomena=napomena,
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
    mbo: str = Query(..., description="Patient MBO"),
    current_user: User = Depends(require_roles("admin", "doctor", "nurse")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    cases = await cezih.dispatch_retrieve_cases(
        mbo,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
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
    org_code, source_oid = await _get_tenant_cezih_config(db, current_user.tenant_id)
    return await cezih.dispatch_create_case(
        data.patient_mbo, current_user.practitioner_id or "",
        org_code,
        data.icd_code, data.icd_display, data.onset_date,
        data.verification_status, data.note,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
        source_oid=source_oid,
    )


@router.put("/cases/{case_id}/status", response_model=CaseActionResponse)
async def update_case_status(
    request: Request,
    case_id: str,
    data: UpdateCaseStatusRequest,
    mbo: str = Query(..., description="Patient MBO"),
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid = await _get_tenant_cezih_config(db, current_user.tenant_id)
    return await cezih.dispatch_update_case(
        case_id, mbo, current_user.practitioner_id or "",
        org_code,
        data.action,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
        source_oid=source_oid,
    )


@router.put("/cases/{case_id}/data", response_model=CaseActionResponse)
async def update_case_data(
    request: Request,
    case_id: str,
    data: UpdateCaseDataRequest,
    mbo: str = Query(..., description="Patient MBO"),
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid = await _get_tenant_cezih_config(db, current_user.tenant_id)
    return await cezih.dispatch_update_case_data(
        case_id, mbo, current_user.practitioner_id or "",
        org_code,
        current_clinical_status=data.current_clinical_status,
        verification_status=data.verification_status,
        icd_code=data.icd_code, icd_display=data.icd_display,
        onset_date=data.onset_date, abatement_date=data.abatement_date,
        note_text=data.note,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
        source_oid=source_oid,
    )


# ============================================================
# TC19-22: Document Operations
# ============================================================


@router.get("/documents", response_model=list[DocumentSearchItem])
async def search_documents(
    request: Request,
    mbo: str = Query(None, description="Patient MBO"),
    type: str = Query(None, description="Document type (nalaz, uputnica)"),
    date_from: str = Query(None, description="Date from (YYYY-MM-DD)"),
    date_to: str = Query(None, description="Date to (YYYY-MM-DD)"),
    status: str = Query(None, description="FHIR status (current, superseded, entered-in-error)"),
    current_user: User = Depends(require_roles("admin", "doctor", "nurse")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    return await cezih.dispatch_search_documents(
        patient_mbo=mbo, document_type=type,
        date_from=date_from, date_to=date_to, status_filter=status,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
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
    org_code, source_oid = await _get_tenant_cezih_config(db, current_user.tenant_id)
    practitioner_name = f"{current_user.ime} {current_user.prezime}".strip() if hasattr(current_user, "ime") else ""
    return await cezih.dispatch_replace_document(
        reference_id,
        record_id=data.record_id if data else None,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
        org_code=org_code,
        practitioner_id=current_user.practitioner_id,
        practitioner_name=practitioner_name,
        encounter_id=data.encounter_id if data else "",
        case_id=data.case_id if data else "",
    )


@router.delete("/e-nalaz/{reference_id}", response_model=DocumentActionResponse)
async def cancel_document(
    request: Request,
    reference_id: str,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid = await _get_tenant_cezih_config(db, current_user.tenant_id)
    practitioner_name = f"{current_user.ime} {current_user.prezime}".strip() if hasattr(current_user, "ime") else ""
    return await cezih.dispatch_cancel_document(
        reference_id,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
        org_code=org_code,
        practitioner_id=current_user.practitioner_id,
        practitioner_name=practitioner_name,
    )


@router.get("/e-nalaz/{reference_id}/document")
async def retrieve_document(
    request: Request,
    reference_id: str,
    url: str = Query(None, description="CEZIH content URL from DocumentReference"),
    current_user: User = Depends(require_roles("admin", "doctor", "nurse")),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response

    await check_cezih_access(db, current_user.tenant_id)
    content = await cezih.dispatch_retrieve_document(
        reference_id,
        document_url=url,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )
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
    mbo: str = Query(...),
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    visits = await cezih.dispatch_list_visits(
        mbo, db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
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
    org_code, source_oid = await _get_tenant_cezih_config(db, current_user.tenant_id)
    return await cezih.dispatch_create_visit(
        data.patient_mbo, data.nacin_prijema, data.vrsta_posjete, data.tip_posjete, data.reason,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
        practitioner_id=current_user.practitioner_id or "",
        org_code=org_code, source_oid=source_oid,
    )


@router.patch("/visits/{visit_id}", response_model=VisitResponse)
async def update_visit(
    request: Request,
    visit_id: str,
    data: UpdateVisitRequest,
    mbo: str = Query(..., min_length=1, description="Patient MBO"),
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid = await _get_tenant_cezih_config(db, current_user.tenant_id)
    return await cezih.dispatch_update_visit(
        visit_id, mbo, data.reason,
        nacin_prijema=data.nacin_prijema,
        vrsta_posjete=data.vrsta_posjete,
        tip_posjete=data.tip_posjete,
        diagnosis_case_id=data.diagnosis_case_id,
        additional_practitioner_id=data.additional_practitioner_id,
        period_start=data.period_start,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
        practitioner_id=current_user.practitioner_id or "",
        org_code=org_code, source_oid=source_oid,
    )


@router.post("/visits/{visit_id}/action", response_model=VisitResponse)
async def visit_action(
    request: Request,
    visit_id: str,
    data: VisitActionRequest,
    mbo: str = Query(..., min_length=1, description="Patient MBO"),
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid = await _get_tenant_cezih_config(db, current_user.tenant_id)
    return await cezih.dispatch_visit_action(
        visit_id, data.action, mbo,
        period_start=data.period_start,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
        practitioner_id=current_user.practitioner_id or "",
        org_code=org_code, source_oid=source_oid,
    )


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
