import json  # noqa: F401
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.plan_enforcement import check_cezih_access
from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models.audit_log import AuditLog
from app.models.cezih_euputnica import CezihEUputnica
from app.models.medical_record import MedicalRecord
from app.models.user import User
from app.schemas.cezih import (
    CaseActionResponse,
    CaseItem,
    CaseResponse,
    CasesListResponse,
    CezihActivityItem,
    CezihActivityListResponse,
    CezihDashboardStats,
    CezihStatusResponse,
    CloseVisitRequest,
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
    EUputniceResponse,
    ForeignerRegistrationRequest,
    ForeignerRegistrationResponse,
    InsuranceCheckRequest,
    InsuranceCheckResponse,
    LijekItem,
    OidLookupRequest,
    OidLookupResponse,
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
    VisitActionResponse,
    VisitResponse,
)
from app.services.cezih import dispatcher as cezih

router = APIRouter(prefix="/cezih", tags=["cezih"])


def _http_client(request: Request):
    return request.app.state.http_client


@router.get("/status", response_model=CezihStatusResponse)
async def get_cezih_status(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return await cezih.cezih_status(current_user.tenant_id, http_client=_http_client(request))


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
    return await cezih.send_enalaz(
        db, current_user.tenant_id, data.patient_id, data.record_id,
        user_id=current_user.id, uputnica_id=data.uputnica_id,
        http_client=_http_client(request),
    )


@router.get("/e-uputnice", response_model=EUputniceResponse)
async def list_euputnice(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all persisted e-Uputnice for the tenant."""
    return await cezih.get_stored_euputnice(db=db, tenant_id=current_user.tenant_id)


@router.post("/e-uputnica/preuzmi", response_model=EUputniceResponse)
async def retrieve_euputnice(
    request: Request,
    current_user: User = Depends(require_roles("admin", "doctor", "nurse")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    return await cezih.retrieve_euputnice(
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )


@router.post("/e-recept", response_model=EReceptResponse)
async def send_erecept(
    request: Request,
    data: EReceptRequest,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
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

    # Insurance: find the most recent insurance check in audit log
    ins_result = await db.execute(
        select(AuditLog).where(
            AuditLog.tenant_id == current_user.tenant_id,
            AuditLog.resource_type == "cezih",
            AuditLog.action == "insurance_check",
        ).order_by(AuditLog.created_at.desc()).limit(1)
    )
    ins_log = ins_result.scalar_one_or_none()

    insurance = PatientCezihInsurance()
    if ins_log and ins_log.details:
        ins_details = json.loads(ins_log.details)
        insurance = PatientCezihInsurance(
            mbo=ins_details.get("mbo"),
            status_osiguranja=ins_details.get("result"),
            last_checked=ins_log.created_at,
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

    # Open referrals count from persisted data
    open_result = await db.execute(
        select(func.count()).where(
            CezihEUputnica.tenant_id == current_user.tenant_id,
            CezihEUputnica.status == "Otvorena",
        )
    )
    open_count = open_result.scalar() or 0

    return CezihDashboardStats(
        danas_operacije=danas,
        otvorene_uputnice=open_count,
        zadnja_operacija=last_op,
    )


# --- Feature 4: Drug Search ---


@router.get("/lijekovi", response_model=list[LijekItem])
async def search_drugs(
    q: str = Query("", min_length=0),
    current_user: User = Depends(get_current_user),
):
    return cezih.drug_search(q)


# ============================================================
# TC6: OID Registry Lookup
# ============================================================


@router.post("/oid-lookup", response_model=OidLookupResponse)
async def oid_lookup(
    request: Request,
    data: OidLookupRequest,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    return await cezih.oid_lookup(
        data.oid,
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
# TC11: Foreigner Registration (PMIR)
# ============================================================


@router.post("/patients/foreigner", response_model=ForeignerRegistrationResponse)
async def register_foreigner(
    request: Request,
    data: ForeignerRegistrationRequest,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    return await cezih.foreigner_registration(
        data.model_dump(),
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )


# ============================================================
# TC12-14: Visit Management
# ============================================================


@router.post("/visits", response_model=VisitResponse)
async def create_visit(
    request: Request,
    data: CreateVisitRequest,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    return await cezih.dispatch_create_visit(
        data.patient_mbo, current_user.practitioner_id or "",
        settings.CEZIH_ORG_CODE,
        data.period_start, data.admission_type_code,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )


@router.put("/visits/{visit_id}", response_model=VisitActionResponse)
async def update_visit(
    request: Request,
    visit_id: str,
    data: UpdateVisitRequest,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    return await cezih.dispatch_update_visit(
        visit_id, current_user.practitioner_id or "",
        settings.CEZIH_ORG_CODE,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
        **updates,
    )


@router.post("/visits/{visit_id}/close", response_model=VisitActionResponse)
async def close_visit(
    request: Request,
    visit_id: str,
    data: CloseVisitRequest,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    return await cezih.dispatch_close_visit(
        visit_id, current_user.practitioner_id or "",
        settings.CEZIH_ORG_CODE,
        data.period_end, data.period_end,  # period_start not needed for close
        diagnosis_case_id=data.diagnosis_case_id,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )


@router.post("/visits/{visit_id}/reopen", response_model=VisitActionResponse)
async def reopen_visit(
    request: Request,
    visit_id: str,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    return await cezih.dispatch_reopen_visit(
        visit_id, current_user.practitioner_id or "",
        settings.CEZIH_ORG_CODE,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )


@router.delete("/visits/{visit_id}", response_model=VisitActionResponse)
async def cancel_visit(
    request: Request,
    visit_id: str,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    return await cezih.dispatch_cancel_visit(
        visit_id, current_user.practitioner_id or "",
        settings.CEZIH_ORG_CODE,
        period_start="",  # Server already has this
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )


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
    return await cezih.dispatch_create_case(
        data.patient_mbo, current_user.practitioner_id or "",
        settings.CEZIH_ORG_CODE,
        data.icd_code, data.icd_display, data.onset_date,
        data.verification_status, data.note,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
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
    return await cezih.dispatch_update_case(
        case_id, mbo, current_user.practitioner_id or "",
        settings.CEZIH_ORG_CODE,
        data.action,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
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
    return await cezih.dispatch_update_case_data(
        case_id, mbo, current_user.practitioner_id or "",
        settings.CEZIH_ORG_CODE,
        current_clinical_status=data.current_clinical_status,
        verification_status=data.verification_status,
        icd_code=data.icd_code, icd_display=data.icd_display,
        onset_date=data.onset_date, abatement_date=data.abatement_date,
        note_text=data.note,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
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
    return await cezih.dispatch_replace_document(
        reference_id,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )


@router.delete("/e-nalaz/{reference_id}", response_model=DocumentActionResponse)
async def cancel_document(
    request: Request,
    reference_id: str,
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    return await cezih.dispatch_cancel_document(
        reference_id,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )


@router.get("/e-nalaz/{reference_id}/document")
async def retrieve_document(
    request: Request,
    reference_id: str,
    current_user: User = Depends(require_roles("admin", "doctor", "nurse")),
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response

    await check_cezih_access(db, current_user.tenant_id)
    content = await cezih.dispatch_retrieve_document(
        reference_id,
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=cezih-{reference_id}.pdf"},
    )
