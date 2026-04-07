from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class InsuranceCheckRequest(BaseModel):
    mbo: str


class InsuranceCheckResponse(BaseModel):
    mock: bool = True
    mbo: str
    ime: str
    prezime: str
    datum_rodjenja: str
    osiguravatelj: str
    status_osiguranja: str
    broj_osiguranja: str


class ENalazRequest(BaseModel):
    patient_id: UUID
    record_id: UUID


class ENalazResponse(BaseModel):
    mock: bool = True
    success: bool
    reference_id: str
    sent_at: datetime


class EReceptLijekEntry(BaseModel):
    atk: str
    naziv: str
    kolicina: int = 1
    doziranje: str = ""
    napomena: str = ""


class EReceptRequest(BaseModel):
    patient_id: UUID
    lijekovi: list[EReceptLijekEntry]


class EReceptResponse(BaseModel):
    mock: bool = True
    success: bool
    recept_id: str


class EReceptStornoResponse(BaseModel):
    mock: bool = True
    success: bool
    recept_id: str
    status: str


class CezihStatusResponse(BaseModel):
    mock: bool = True
    connected: bool
    mode: str
    agent_connected: bool
    last_heartbeat: datetime | None
    # TODO: When AKD smart card auth is live, populate from card identity
    # instead of current logged-in user. The local agent should send the
    # authenticated practitioner name + clinic after VPN+card handshake.
    connected_doctor: str | None = None
    connected_clinic: str | None = None


# --- Feature 1: Activity Log ---


class CezihActivityItem(BaseModel):
    id: str
    action: str
    resource_id: str | None = None
    details: str | None = None
    created_at: datetime
    user_id: str | None = None


class CezihActivityListResponse(BaseModel):
    items: list[CezihActivityItem]
    total: int


# --- Feature 2: Patient CEZIH Summary ---


class PatientCezihInsurance(BaseModel):
    mbo: str | None = None
    status_osiguranja: str | None = None
    osiguravatelj: str | None = None
    last_checked: datetime | None = None


class PatientCezihENalaz(BaseModel):
    record_id: str
    datum: datetime
    tip: str
    reference_id: str | None = None
    cezih_sent_at: datetime | None = None
    cezih_storno: bool = False
    cezih_signed: bool = False
    cezih_signed_at: datetime | None = None


class PatientCezihERecept(BaseModel):
    recept_id: str
    datum: datetime
    lijekovi: list[str] = []


class PatientCezihSummary(BaseModel):
    mock: bool = True
    insurance: PatientCezihInsurance
    e_nalaz_history: list[PatientCezihENalaz] = []
    e_recept_history: list[PatientCezihERecept] = []


# --- Feature 3: Dashboard Stats ---


class CezihDashboardStats(BaseModel):
    mock: bool = True
    danas_operacije: int = 0
    neposlani_nalazi: int = 0
    zadnja_operacija: datetime | None = None


# --- Feature 4: Drug Search ---


class LijekItem(BaseModel):
    atk: str
    naziv: str
    oblik: str
    jacina: str


# ============================================================
# TC6: OID Registry
# ============================================================


class OidLookupRequest(BaseModel):
    oid: str


class OidLookupResponse(BaseModel):
    mock: bool = True
    oid: str
    name: str
    responsible_org: str
    status: str


# ============================================================
# TC7: Code System Query
# ============================================================


class CodeSystemItem(BaseModel):
    mock: bool = True
    code: str
    display: str
    system: str


# ============================================================
# TC8: Value Set Expand
# ============================================================


class ValueSetConceptItem(BaseModel):
    code: str
    display: str
    system: str


class ValueSetExpandResponse(BaseModel):
    mock: bool = True
    url: str
    concepts: list[ValueSetConceptItem]
    total: int


# ============================================================
# TC9: Subject Registry
# ============================================================


class OrganizationItem(BaseModel):
    mock: bool = True
    id: str
    name: str
    hzzo_code: str
    active: bool


class PractitionerItem(BaseModel):
    mock: bool = True
    id: str
    family: str
    given: str
    hzjz_id: str
    active: bool


# ============================================================
# TC11: Foreigner Registration
# ============================================================


class ForeignerRegistrationRequest(BaseModel):
    ime: str
    prezime: str
    datum_rodjenja: str
    spol: str = "unknown"
    drzavljanstvo: str = ""
    broj_putovnice: str | None = None
    ehic_broj: str | None = None


class ForeignerRegistrationResponse(BaseModel):
    mock: bool = True
    success: bool
    patient_id: str
    mbo: str
    local_patient_id: UUID | None = None


# ============================================================
# TC12-14: Visit Management
# ============================================================


class CreateVisitRequest(BaseModel):
    patient_id: UUID
    patient_mbo: str
    nacin_prijema: str = "6"      # 1-10, default: 6=Ostalo
    vrsta_posjete: str = "1"      # 1-3, default: 1=Pacijent prisutan
    tip_posjete: str = "1"        # 1-3, default: 1=Posjeta LOM
    reason: str | None = None


class UpdateVisitRequest(BaseModel):
    reason: str | None = None


class VisitActionRequest(BaseModel):
    action: str  # close, reopen, storno


class VisitResponse(BaseModel):
    mock: bool = True
    success: bool
    visit_id: str
    status: str  # planned, in-progress, finished, cancelled, entered-in-error


class VisitItem(BaseModel):
    mock: bool = True
    visit_id: str
    patient_mbo: str
    status: str
    visit_type: str
    reason: str | None = None
    period_start: str | None = None
    period_end: str | None = None


class VisitsListResponse(BaseModel):
    mock: bool = True
    visits: list[VisitItem]


# ============================================================
# TC15-17: Case Management
# ============================================================


class CaseItem(BaseModel):
    mock: bool = True
    case_id: str
    icd_code: str
    icd_display: str
    clinical_status: str
    onset_date: str


class CasesListResponse(BaseModel):
    mock: bool = True
    cases: list[CaseItem]


class CreateCaseRequest(BaseModel):
    patient_id: UUID
    patient_mbo: str
    icd_code: str
    icd_display: str
    onset_date: str
    verification_status: str = "unconfirmed"
    note: str | None = None


class CaseResponse(BaseModel):
    mock: bool = True
    success: bool
    local_case_id: str
    cezih_case_id: str


class UpdateCaseStatusRequest(BaseModel):
    action: str  # remission, relapse, resolve, reopen, delete, create_recurring


class UpdateCaseDataRequest(BaseModel):
    current_clinical_status: str | None = None
    verification_status: str | None = None
    icd_code: str | None = None
    icd_display: str | None = None
    onset_date: str | None = None
    abatement_date: str | None = None
    note: str | None = None


class CaseActionResponse(BaseModel):
    mock: bool = True
    success: bool
    case_id: str | None = None
    action: str | None = None


# ============================================================
# TC19-22: Document Operations
# ============================================================


class ReplaceDocumentRequest(BaseModel):
    patient_id: UUID | None = None
    record_id: UUID | None = None


class DocumentActionResponse(BaseModel):
    mock: bool = True
    success: bool
    reference_id: str | None = None
    new_reference_id: str | None = None
    replaced_reference_id: str | None = None
    status: str | None = None


class DocumentSearchItem(BaseModel):
    mock: bool = True
    id: str
    datum_izdavanja: str
    izdavatelj: str
    svrha: str
    specijalist: str
    status: str
    type: str | None = None
