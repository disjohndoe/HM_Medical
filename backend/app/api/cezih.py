import json  # noqa: F401
import logging
from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import status as http_status
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
        data.identifier_type, data.identifier_value,
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
    if data.patient_id is not None:
        return await cezih.insurance_check(
            data.patient_id,
            db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
            http_client=_http_client(request),
        )
    if data.identifier_type and data.identifier_value:
        return await cezih.insurance_check_by_identifier(
            data.identifier_type, data.identifier_value,
            db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
            http_client=_http_client(request),
        )
    if data.mbo:
        return await cezih.insurance_check_by_mbo(
            data.mbo,
            db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
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
            document_oid=r.cezih_document_oid,
            cezih_sent_at=r.cezih_sent_at,
            cezih_storno=r.cezih_storno,
            cezih_signed=bool(r.cezih_signature_data),
            cezih_signed_at=r.cezih_signed_at,
            updated_at=r.updated_at,
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
    from app.services.cezih.service import (
        SYS_EUROPSKA,
        SYS_JEDINSTVENI,
        SYS_MBO,
        SYS_OIB,
        SYS_PUTOVNICA,
    )

    filters = []
    for ident in (result.get("identifikatori") or []):
        sys_uri = ident.get("system")
        val = ident.get("value")
        if not sys_uri or not val:
            continue
        if sys_uri == SYS_MBO:
            filters.append(Patient.mbo == val)
        elif sys_uri == SYS_OIB:
            filters.append(Patient.oib == val)
        elif sys_uri == SYS_PUTOVNICA:
            filters.append(Patient.broj_putovnice == val)
        elif sys_uri == SYS_EUROPSKA:
            filters.append(Patient.ehic_broj == val)
        elif sys_uri == SYS_JEDINSTVENI:
            filters.append(Patient.cezih_patient_id == val)
    if result.get("cezih_id"):
        filters.append(Patient.cezih_patient_id == result["cezih_id"])

    if filters:
        lookup = await db.execute(
            select(Patient.id).where(
                Patient.tenant_id == current_user.tenant_id,
                Patient.is_active.is_(True),
                or_(*filters),
            ).limit(1),
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
        # PMIR returns CEZIH's jedinstveni-identifikator-pacijenta in the "mbo" key.
        # Foreigners don't have a Croatian MBO — leave patients.mbo NULL.
        cezih_id = result.get("mbo") or None
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
        data.patient_id, current_user.practitioner_id or "",
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
    patient_id: UUID = Query(..., description="Local patient UUID"),
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid = await _get_tenant_cezih_config(db, current_user.tenant_id)
    return await cezih.dispatch_update_case(
        case_id, patient_id, current_user.practitioner_id or "",
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
    patient_id: UUID = Query(..., description="Local patient UUID"),
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid = await _get_tenant_cezih_config(db, current_user.tenant_id)
    return await cezih.dispatch_update_case_data(
        case_id, patient_id, current_user.practitioner_id or "",
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
        patient_id=patient_id, document_type=type,
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
        db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
        http_client=_http_client(request),
    )
    original_size = len(content)
    is_pdf = content.startswith(b"%PDF")

    if not is_pdf:
        # CEZIH returned non-PDF content — likely an error or empty response
        text_preview = content.decode("utf-8", errors="replace")[:500]
        logger.warning(
            "CEZIH document %s: NOT PDF (%d bytes), wrapping as PDF. Content preview: %r",
            reference_id, original_size, text_preview,
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
        patient_id, db=db, user_id=current_user.id, tenant_id=current_user.tenant_id,
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
        data.patient_id, data.nacin_prijema, data.vrsta_posjete, data.tip_posjete, data.reason,
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
    patient_id: UUID = Query(..., description="Local patient UUID"),
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid = await _get_tenant_cezih_config(db, current_user.tenant_id)
    return await cezih.dispatch_update_visit(
        visit_id, patient_id, data.reason,
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
    patient_id: UUID = Query(..., description="Local patient UUID"),
    current_user: User = Depends(require_roles("admin", "doctor")),
    db: AsyncSession = Depends(get_db),
):
    await check_cezih_access(db, current_user.tenant_id)
    org_code, source_oid = await _get_tenant_cezih_config(db, current_user.tenant_id)
    return await cezih.dispatch_visit_action(
        visit_id, data.action, patient_id,
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
