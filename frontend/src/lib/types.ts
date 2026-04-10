export interface Tenant {
  id: string;
  naziv: string;
  vrsta: string;
  email: string;
  telefon: string | null;
  adresa: string | null;
  oib: string | null;
  grad: string | null;
  postanski_broj: string | null;
  zupanija: string | null;
  web: string | null;
  sifra_ustanove: string | null;
  oid: string | null;
  plan_tier: string;
  trial_expires_at: string | null;
  is_active: boolean;
  cezih_status: string;
  has_hzzo_contract: boolean;
}

export interface User {
  id: string;
  email: string;
  ime: string;
  prezime: string;
  titula: string | null;
  telefon: string | null;
  role: string;
  is_active: boolean;
  last_login_at: string | null;
  tenant_id: string;
  created_at: string;
  card_holder_name: string | null;
  card_certificate_oib: string | null;
  practitioner_id: string | null;
  tenant?: Tenant;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User | null;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  naziv_klinike: string;
  vrsta: string;
  email: string;
  password: string;
  ime: string;
  prezime: string;
}

export interface UserCreate {
  email: string;
  password: string;
  ime: string;
  prezime: string;
  titula?: string;
  telefon?: string;
  role: string;
  practitioner_id?: string | null;
}

export interface CezihPatientImport {
  id: string;
  ime: string;
  prezime: string;
  datum_rodjenja: string | null;
  oib: string | null;
  spol: string | null;
  mbo: string;
}

export interface Patient {
  id: string;
  ime: string;
  prezime: string;
  datum_rodjenja: string | null;
  spol: string | null;
  oib: string | null;
  mbo: string | null;
  adresa: string | null;
  grad: string | null;
  postanski_broj: string | null;
  telefon: string | null;
  mobitel: string | null;
  email: string | null;
  napomena: string | null;
  alergije: string | null;
  is_active: boolean;
  tenant_id: string;
  created_at: string;
  updated_at: string;
  cezih_insurance_status: string | null;
  cezih_insurance_checked_at: string | null;
}

export interface PatientCreate {
  ime: string;
  prezime: string;
  datum_rodjenja?: string | null;
  spol?: string | null;
  oib?: string | null;
  mbo?: string | null;
  adresa?: string | null;
  grad?: string | null;
  postanski_broj?: string | null;
  telefon?: string | null;
  mobitel?: string | null;
  email?: string | null;
  napomena?: string | null;
  alergije?: string | null;
}

export interface PatientUpdate {
  ime?: string | null;
  prezime?: string | null;
  datum_rodjenja?: string | null;
  spol?: string | null;
  oib?: string | null;
  mbo?: string | null;
  adresa?: string | null;
  grad?: string | null;
  postanski_broj?: string | null;
  telefon?: string | null;
  mobitel?: string | null;
  email?: string | null;
  napomena?: string | null;
  alergije?: string | null;
  is_active?: boolean | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}

export type AppointmentStatus = "zakazan" | "potvrdjen" | "u_tijeku" | "zavrsen" | "otkazan" | "nije_dosao";
export type AppointmentVrsta = "pregled" | "kontrola" | "lijecenje" | "higijena" | "konzultacija" | "hitno";

export interface Appointment {
  id: string;
  tenant_id: string;
  patient_id: string;
  doktor_id: string;
  datum_vrijeme: string;
  trajanje_minuta: number;
  status: AppointmentStatus;
  vrsta: AppointmentVrsta;
  napomena: string | null;
  patient_ime?: string | null;
  patient_prezime?: string | null;
  doktor_ime?: string | null;
  doktor_prezime?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AppointmentCreate {
  patient_id: string;
  doktor_id: string;
  datum_vrijeme: string;
  trajanje_minuta?: number;
  vrsta?: string;
  napomena?: string;
}

export interface AvailableSlot {
  start: string;
  end: string;
}

// --- Procedures ---

export interface Procedure {
  id: string;
  sifra: string;
  naziv: string;
  opis: string | null;
  cijena_cents: number;
  trajanje_minuta: number;
  kategorija: string;
  is_active: boolean;
  tenant_id: string;
  created_at: string;
  updated_at: string;
}

export interface ProcedureCreate {
  sifra: string;
  naziv: string;
  opis?: string | null;
  cijena_cents?: number;
  trajanje_minuta?: number;
  kategorija: string;
}

export interface ProcedureUpdate {
  sifra?: string | null;
  naziv?: string | null;
  opis?: string | null;
  cijena_cents?: number | null;
  trajanje_minuta?: number | null;
  kategorija?: string | null;
  is_active?: boolean | null;
}

export interface PerformedProcedure {
  id: string;
  patient_id: string;
  appointment_id: string | null;
  medical_record_id: string | null;
  procedure_id: string;
  doktor_id: string;
  lokacija: string | null;
  datum: string;
  cijena_cents: number;
  napomena: string | null;
  procedure_naziv: string | null;
  procedure_sifra: string | null;
  doktor_ime: string | null;
  doktor_prezime: string | null;
  tenant_id: string;
  created_at: string;
  updated_at: string;
}

export interface PerformedProcedureCreate {
  patient_id: string;
  procedure_id: string;
  appointment_id?: string | null;
  medical_record_id?: string | null;
  lokacija?: string | null;
  datum: string;
  cijena_cents?: number | null;
  napomena?: string | null;
}

// --- Medical Records ---

// System types only — custom types are dynamically configured per tenant
export type RecordTip =
  | "ambulantno_izvjesce"
  | "specijalisticki_nalaz"
  | "otpusno_pismo"
  | "nalaz"
  | "dijagnoza"
  | "misljenje"
  | "preporuka"
  | "epikriza"
  | "anamneza";

// --- Record Types (tenant-configurable) ---

export interface RecordType {
  id: string;
  tenant_id: string;
  slug: string;
  label: string;
  color: string | null;
  is_system: boolean;
  is_cezih_mandatory: boolean;
  is_cezih_eligible: boolean;
  is_active: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface RecordTypeCreate {
  slug: string;
  label: string;
  color?: string | null;
  sort_order?: number;
}

export interface RecordTypeUpdate {
  label?: string | null;
  color?: string | null;
  is_active?: boolean | null;
  sort_order?: number | null;
}

export interface MedicalRecord {
  id: string;
  patient_id: string;
  doktor_id: string;
  appointment_id: string | null;
  datum: string;
  tip: string;
  dijagnoza_mkb: string | null;
  dijagnoza_tekst: string | null;
  sadrzaj: string;
  cezih_sent: boolean;
  cezih_sent_at: string | null;
  cezih_reference_id: string | null;
  cezih_storno: boolean;
  sensitivity: string;
  preporucena_terapija: PreporucenaTerapijaEntry[] | null;
  doktor_ime: string | null;
  doktor_prezime: string | null;
  patient_ime: string | null;
  patient_prezime: string | null;
  tenant_id: string;
  created_at: string;
  updated_at: string;
}

export interface MedicalRecordCreate {
  patient_id: string;
  appointment_id?: string | null;
  datum: string;
  tip: string;
  dijagnoza_mkb?: string | null;
  dijagnoza_tekst?: string | null;
  sadrzaj: string;
  sensitivity?: string;
  preporucena_terapija?: PreporucenaTerapijaEntry[] | null;
}

export interface MedicalRecordUpdate {
  appointment_id?: string | null;
  datum?: string | null;
  tip?: string | null;
  dijagnoza_mkb?: string | null;
  dijagnoza_tekst?: string | null;
  sadrzaj?: string | null;
  sensitivity?: string | null;
  preporucena_terapija?: PreporucenaTerapijaEntry[] | null;
}

export interface PreporucenaTerapijaEntry {
  atk: string;
  naziv: string;
  jacina: string;
  oblik: string;
  doziranje: string;
  napomena: string;
}

// --- Bilješke (Clinical Notes) ---

export type BiljeskaKategorija = "opca" | "anamneza" | "dijagnoza" | "terapija" | "napredak" | "ostalo";

export interface Biljeska {
  id: string;
  patient_id: string;
  doktor_id: string;
  datum: string;
  naslov: string;
  sadrzaj: string;
  kategorija: BiljeskaKategorija;
  is_pinned: boolean;
  doktor_ime: string | null;
  doktor_prezime: string | null;
  tenant_id: string;
  created_at: string;
  updated_at: string;
}

export interface BiljeskaCreate {
  patient_id: string;
  datum: string;
  naslov: string;
  sadrzaj: string;
  kategorija?: string;
}

export interface BiljeskaUpdate {
  datum?: string | null;
  naslov?: string | null;
  sadrzaj?: string | null;
  kategorija?: string | null;
  is_pinned?: boolean | null;
}

// --- Dashboard ---

export interface DashboardStats {
  danas_termini: number;
  ukupno_pacijenti: number;
  ovaj_tjedan_termini: number;
  novi_pacijenti_mjesec: number;
  cezih_status: string;
}

export interface TodayAppointment {
  id: string;
  patient_id: string;
  datum_vrijeme: string;
  trajanje_minuta: number;
  status: AppointmentStatus;
  vrsta: AppointmentVrsta;
  patient_ime: string | null;
  patient_prezime: string | null;
  doktor_ime: string | null;
  doktor_prezime: string | null;
}

// --- Documents ---

export interface Document {
  id: string;
  patient_id: string;
  naziv: string;
  kategorija: string;
  file_size: number;
  mime_type: string;
  uploaded_by: string;
  created_at: string;
}

export interface DocumentUploadResponse {
  id: string;
  patient_id: string;
  naziv: string;
  kategorija: string;
  file_size: number;
  mime_type: string;
  created_at: string;
}

// --- Plan Usage ---

export interface PlanUsage {
  plan_tier: string;
  users: { current: number; max: number };
  patients: { current: number; max: number | null };
  sessions: { current: number; max: number };
  cezih_access: boolean;
  trial_days_remaining: number | null;
}

// --- Agent ---

export interface AgentSecretResponse {
  agent_secret: string;
  tenant_id: string;
}

export interface PairingTokenResponse {
  pairing_url: string;
  pairing_token: string;
}

// --- Card Status ---

export interface CardStatusResponse {
  agent_connected: boolean;
  agents_count: number;
  card_inserted: boolean;
  card_holder: string | null;
  vpn_connected: boolean;
  matched_doctor_id: string | null;
  matched_doctor_name: string | null;
}

// --- CEZIH ---

export interface CezihStatusResponse {
  connected: boolean;
  agent_connected: boolean;
  last_heartbeat: string | null;
  connected_doctor: string | null;
  connected_clinic: string | null;
  card_inserted: boolean;
  vpn_connected: boolean;
  reader_available: boolean;
  card_holder: string | null;
}

export interface InsuranceCheckResponse {

  mbo: string;
  ime: string;
  prezime: string;
  datum_rodjenja: string;
  oib: string;
  spol: string;
  osiguravatelj: string;
  status_osiguranja: string;
}

export interface ENalazResponse {

  success: boolean;
  reference_id: string;
  sent_at: string;
}

export interface EReceptLijekEntry {
  atk: string;
  naziv: string;
  kolicina: number;
  doziranje: string;
  napomena: string;
}

export interface EReceptResponse {

  success: boolean;
  recept_id: string;
}

export interface EReceptStornoResponse {

  success: boolean;
  recept_id: string;
  status: string;
}

// --- Prescriptions ---

export interface PrescriptionLijekEntry {
  atk: string;
  naziv: string;
  oblik: string;
  jacina: string;
  kolicina: number;
  doziranje: string;
  napomena: string;
}

export interface Prescription {
  id: string;
  patient_id: string;
  doktor_id: string;
  medical_record_id: string | null;
  lijekovi: PrescriptionLijekEntry[];
  cezih_sent: boolean;
  cezih_sent_at: string | null;
  cezih_recept_id: string | null;
  cezih_storno: boolean;
  cezih_storno_at: string | null;
  napomena: string | null;
  doktor_ime: string | null;
  doktor_prezime: string | null;
  tenant_id: string;
  created_at: string;
  updated_at: string;
}

export interface PrescriptionCreate {
  patient_id: string;
  medical_record_id?: string | null;
  lijekovi: Omit<PrescriptionLijekEntry, "oblik" | "jacina">[];
  napomena?: string | null;
}

export interface PrescriptionSendResponse {
  prescription_id: string;
  cezih_recept_id: string;
  success: boolean;

}

// --- CEZIH Activity Log ---

export interface CezihActivityItem {
  id: string;
  action: string;
  resource_id: string | null;
  details: string | null;
  created_at: string;
  user_id: string | null;
}

export interface CezihActivityListResponse {
  items: CezihActivityItem[];
  total: number;
}

// --- Patient CEZIH Summary ---

export interface PatientCezihInsurance {
  mbo: string | null;
  status_osiguranja: string | null;
  osiguravatelj: string | null;
  broj_osiguranja: string | null;
  last_checked: string | null;
}

export interface PatientCezihENalaz {
  record_id: string;
  datum: string;
  tip: string;
  reference_id: string | null;
  cezih_sent_at: string | null;
  cezih_storno: boolean;
  cezih_signed: boolean;
  cezih_signed_at: string | null;
}

export interface PatientCezihERecept {
  recept_id: string;
  datum: string;
  lijekovi: string[];
}

export interface PatientCezihSummary {

  insurance: PatientCezihInsurance;
  e_nalaz_history: PatientCezihENalaz[];
  e_recept_history: PatientCezihERecept[];
}

// --- CEZIH Dashboard Stats ---

export interface CezihDashboardStats {

  danas_operacije: number;
  neposlani_nalazi: number;
  zadnja_operacija: string | null;
}

// --- Drug Search ---

export interface LijekItem {
  atk: string;
  naziv: string;
  oblik: string;
  jacina: string;
}

// ============================================================
// TC6: OID Registry
// ============================================================

export interface OidLookupResponse {

  oid: string;
  name: string;
  responsible_org: string;
  status: string;
}

// ============================================================
// TC7: Code System Query
// ============================================================

export interface CodeSystemItem {

  code: string;
  display: string;
  system: string;
}

// ============================================================
// TC8: Value Set Expand
// ============================================================

export interface ValueSetExpandResponse {

  url: string;
  concepts: { code: string; display: string; system: string }[];
  total: number;
}

// ============================================================
// TC9: Subject Registry
// ============================================================

export interface OrganizationItem {

  id: string;
  name: string;
  hzzo_code: string;
  active: boolean;
}

export interface PractitionerItem {

  id: string;
  family: string;
  given: string;
  hzjz_id: string;
  active: boolean;
}

// ============================================================
// TC11: Foreigner Registration
// ============================================================

export interface ForeignerRegistrationRequest {
  ime: string;
  prezime: string;
  datum_rodjenja: string;
  spol?: string;
  drzavljanstvo?: string;
  broj_putovnice?: string;
  ehic_broj?: string;
}

export interface ForeignerRegistrationResponse {

  success: boolean;
  patient_id: string;
  mbo: string;
}

// ============================================================
// TC15-17: Case Management
// ============================================================

export interface CaseItem {

  case_id: string;
  icd_code: string;
  icd_display: string;
  clinical_status: string;
  verification_status: string | null;
  onset_date: string;
  abatement_date: string | null;
  note: string | null;
}

export interface CasesListResponse {

  cases: CaseItem[];
}

export interface CreateCaseRequest {
  patient_id: string;
  patient_mbo: string;
  icd_code: string;
  icd_display: string;
  onset_date: string;
  verification_status?: string;
  note?: string;
}

export interface CaseResponse {

  success: boolean;
  local_case_id: string;
  cezih_case_id: string;
}

export interface CaseActionResponse {

  success: boolean;
  case_id?: string;
  action?: string;
}

// ============================================================
// TC19-22: Document Operations
// ============================================================

// --- TC12-14: Visit Management ---

export interface VisitItem {

  visit_id: string;
  patient_mbo: string;
  status: string;
  visit_type: string;
  visit_type_display: string | null;
  reason: string | null;
  period_start: string | null;
  period_end: string | null;
  service_provider_code: string | null;
  practitioner_id: string | null;
  practitioner_ids: string[];
  diagnosis_case_ids: string[];
}

export interface VisitsListResponse {

  visits: VisitItem[];
}

export interface VisitResponse {

  success: boolean;
  visit_id: string;
  status: string;
}

export interface CreateVisitRequest {
  patient_id: string;
  patient_mbo: string;
  nacin_prijema?: string;   // 1-10, default: "6" (Ostalo)
  vrsta_posjete?: string;   // 1-3, default: "1" (Pacijent prisutan)
  tip_posjete?: string;     // 1-3, default: "1" (Posjeta LOM)
  reason?: string;
}

export interface DocumentSearchItem {

  id: string;
  datum_izdavanja: string;
  izdavatelj: string;
  svrha: string;
  specijalist: string;
  status: string;
  type?: string;
}

export interface DocumentActionResponse {

  success: boolean;
  reference_id?: string;
  new_reference_id?: string;
  replaced_reference_id?: string;
  status?: string;
}

// ---------------------------------------------------------------------------
// Predračun (proforma invoice)
// ---------------------------------------------------------------------------
export interface PredracunStavka {
  id: string;
  sifra: string;
  naziv: string;
  datum: string;
  cijena_cents: number;
}

export interface Predracun {
  id: string;
  patient_id: string;
  broj: string;
  datum: string;
  ukupno_cents: number;
  napomena: string | null;
  created_at: string;
  stavke: PredracunStavka[];
}

export interface PredracunCreate {
  patient_id: string;
  performed_procedure_ids: string[];
  napomena?: string | null;
}
