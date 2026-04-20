export const SPOL_OPTIONS = [
  { value: "M", label: "Muški" },
  { value: "Z", label: "Ženski" },
] as const;

export const APPOINTMENT_STATUS: Record<string, string> = {
  zakazan: "Zakazan",
  potvrdjen: "Potvrđen",
  u_tijeku: "U tijeku",
  zavrsen: "Završen",
  otkazan: "Otkazan",
  nije_dosao: "Nije došao",
};

export const APPOINTMENT_VRSTA: Record<string, string> = {
  pregled: "Pregled",
  kontrola: "Kontrola",
  lijecenje: "Liječenje",
  higijena: "Higijena",
  dijagnostika: "Dijagnostika",
  intervencija: "Intervencija",
  kontrola_nalaza: "Kontrola nalaza",
  konzultacija: "Konzultacija",
  hitno: "Hitno",
};

export const APPOINTMENT_VRSTA_COLORS: Record<string, string> = {
  pregled: "bg-blue-100 border-blue-300 text-blue-900",
  kontrola: "bg-green-100 border-green-300 text-green-900",
  lijecenje: "bg-purple-100 border-purple-300 text-purple-900",
  higijena: "bg-pink-100 border-pink-300 text-pink-900",
  dijagnostika: "bg-cyan-100 border-cyan-300 text-cyan-900",
  intervencija: "bg-orange-100 border-orange-300 text-orange-900",
  kontrola_nalaza: "bg-teal-100 border-teal-300 text-teal-900",
  konzultacija: "bg-amber-100 border-amber-300 text-amber-900",
  hitno: "bg-red-100 border-red-300 text-red-900",
};

export const APPOINTMENT_STATUS_COLORS: Record<string, string> = {
  zakazan: "bg-slate-100 text-slate-700",
  potvrdjen: "bg-blue-100 text-blue-700",
  u_tijeku: "bg-yellow-100 text-yellow-700",
  zavrsen: "bg-green-100 text-green-700",
  otkazan: "bg-red-100 text-red-700",
  nije_dosao: "bg-orange-100 text-orange-700",
};

export const WORKING_HOURS_START = 6;
export const WORKING_HOURS_END = 21;
export const SLOT_GRANULARITY = 15;

export const DURATION_OPTIONS = [15, 30, 45, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330] as const;

// --- Procedures ---

export const PROCEDURE_KATEGORIJA: Record<string, string> = {
  dijagnostika: "Dijagnostika",
  pregled: "Pregled",
  kirurgija: "Kirurgija",
  terapija: "Terapija",
  rehabilitacija: "Rehabilitacija",
  prevencija: "Prevencija",
  estetika: "Estetske procedure",
  laboratorij: "Laboratorijske pretrage",
  pomocne: "Pomoćne procedure",
  ostalo: "Ostalo",
};

export const PROCEDURE_KATEGORIJA_OPTIONS = Object.entries(PROCEDURE_KATEGORIJA).map(
  ([value, label]) => ({ value, label })
);

// --- Medical Records ---
// DEPRECATED: These are kept as fallback defaults only.
// Record types are now tenant-configurable. Use useRecordTypeMaps() hook.
// These constants serve as fallback when API data is not yet loaded.

export const RECORD_TIP: Record<string, string> = {
  // CEZIH mandatory types (čl. 23, NN 14/2019)
  ambulantno_izvjesce: "Ambulantno izvješće",
  specijalisticki_nalaz: "Specijalistički nalaz",
  otpusno_pismo: "Otpusno pismo",
  // General types
  nalaz: "Nalaz",
  dijagnoza: "Dijagnoza",
  misljenje: "Mišljenje",
  preporuka: "Preporuka",
  epikriza: "Epikriza",
  anamneza: "Anamneza",
};

export const RECORD_TIP_OPTIONS = Object.entries(RECORD_TIP).map(
  ([value, label]) => ({ value, label })
);

// Types that must be sent to CEZIH when created
// HRTipDokumenta codes for privatnici: 011 (ambulantno), 012 (specijalisticki/nalaz), 013 (otpusno)
export const CEZIH_MANDATORY_TYPES = new Set([
  "specijalisticki_nalaz",
  "nalaz",
]);

// Types eligible for CEZIH submission
export const CEZIH_ELIGIBLE_TYPES = new Set([
  "ambulantno_izvjesce",
  "specijalisticki_nalaz",
  "otpusno_pismo",
  "nalaz",
  "epikriza",
]);

export const RECORD_TIP_COLORS: Record<string, string> = {
  ambulantno_izvjesce: "bg-emerald-100 text-emerald-800",
  specijalisticki_nalaz: "bg-indigo-100 text-indigo-800",
  otpusno_pismo: "bg-rose-100 text-rose-800",
  nalaz: "bg-blue-100 text-blue-800",
  dijagnoza: "bg-red-100 text-red-800",
  misljenje: "bg-purple-100 text-purple-800",
  preporuka: "bg-green-100 text-green-800",
  epikriza: "bg-amber-100 text-amber-800",
  anamneza: "bg-cyan-100 text-cyan-800",
};

// --- Bilješke (Clinical Notes) ---

export const BILJESKA_KATEGORIJA: Record<string, string> = {
  opca: "Općenito",
  anamneza: "Anamneza",
  dijagnoza: "Dijagnoza",
  terapija: "Terapija",
  napredak: "Napredak",
  ostalo: "Ostalo",
};

export const BILJESKA_KATEGORIJA_OPTIONS = Object.entries(BILJESKA_KATEGORIJA).map(
  ([value, label]) => ({ value, label })
);

export const BILJESKA_KATEGORIJA_COLORS: Record<string, string> = {
  opca: "bg-gray-100 text-gray-800",
  anamneza: "bg-cyan-100 text-cyan-800",
  dijagnoza: "bg-red-100 text-red-800",
  terapija: "bg-green-100 text-green-800",
  napredak: "bg-blue-100 text-blue-800",
  ostalo: "bg-purple-100 text-purple-800",
};

// --- User Roles ---

export const USER_ROLE: Record<string, string> = {
  admin: "Administrator",
  doctor: "Liječnik",
  nurse: "Medicinska sestra",
  receptionist: "Recepcija",
};

export const USER_ROLE_OPTIONS = Object.entries(USER_ROLE).map(
  ([value, label]) => ({ value, label })
);

// --- Doctor identifiers (HZJZ / MBO) ---
// Single source of truth for the format rules enforced on backend (Pydantic)
// and DB (partial unique indexes + role CHECK). Keep in sync with
// backend/app/schemas/user.py and alembic/versions/040_doctor_identifiers.py.

export const DOCTOR_ID_RULES = {
  hzjz: {
    pattern: /^\d{7}$/,
    length: 7,
    message: "HZJZ broj mora imati točno 7 znamenki",
    placeholder: "7 znamenki",
    hint: "Broj zdravstvenog djelatnika iz HZJZ registra (7 znamenki)",
  },
  mbo: {
    pattern: /^\d{9}$/,
    length: 9,
    message: "MBO liječnika mora imati točno 9 znamenki",
    placeholder: "9 znamenki",
    hint: "Matični broj osiguranika liječnika (9 znamenki)",
  },
} as const;

// Roles allowed to hold HZJZ/MBO. Must match the ck_user_role_can_hold_doctor_ids
// CHECK constraint in the DB.
export const ROLES_CAN_HOLD_DOCTOR_IDS = ["doctor", "admin", "nurse"] as const;

// --- CEZIH signing method (per-user preference) ---

export const CEZIH_SIGNING_METHOD: Record<string, string> = {
  smartcard: "Kartica (AKD)",
  extsigner: "Mobitel (Certilia)",
};

export const CEZIH_SIGNING_METHOD_OPTIONS: { value: string; label: string }[] = [
  { value: "extsigner", label: "Mobitel (Certilia)" },
  { value: "smartcard", label: "Kartica (AKD)" },
];

// --- Tenant ---

export const TENANT_VRSTA: Record<string, string> = {
  ordinacija: "Ordinacija",
  poliklinika: "Poliklinika",
  dom_zdravlja: "Dom zdravlja",
};

export const TENANT_VRSTA_OPTIONS = Object.entries(TENANT_VRSTA).map(
  ([value, label]) => ({ value, label })
);

export const PLAN_TIER: Record<string, string> = {
  trial: "Trial",
  solo: "Solo",
  poliklinika: "Poliklinika",
  poliklinika_plus: "Poliklinika+",
};

// --- CEZIH ---

export const CEZIH_STATUS: Record<string, string> = {
  nepovezano: "Nije povezano",
  u_pripremi: "U pripremi",
  testirano: "Testirano",
  certificirano: "Certificirano",
};

export const CEZIH_STATUS_COLORS: Record<string, string> = {
  nepovezano: "bg-muted",
  u_pripremi: "bg-yellow-400",
  testirano: "bg-blue-500",
  certificirano: "bg-green-500",
};

// ISO 3166-1 alpha-3 → Croatian country name. Used for foreign patients'
// drzavljanstvo (e.g. "DEU" → "Njemačka"). Unmapped codes fall back to the
// raw 3-letter code at the call site.
export const COUNTRY_HR: Record<string, string> = {
  HRV: "Hrvatska",
  AUT: "Austrija",
  BIH: "Bosna i Hercegovina",
  BEL: "Belgija",
  BGR: "Bugarska",
  CZE: "Češka",
  DNK: "Danska",
  DEU: "Njemačka",
  ESP: "Španjolska",
  EST: "Estonija",
  FIN: "Finska",
  FRA: "Francuska",
  GBR: "Ujedinjeno Kraljevstvo",
  GRC: "Grčka",
  HUN: "Mađarska",
  IRL: "Irska",
  ITA: "Italija",
  KOS: "Kosovo",
  LUX: "Luksemburg",
  LVA: "Latvija",
  LTU: "Litva",
  MKD: "Sjeverna Makedonija",
  MLT: "Malta",
  MNE: "Crna Gora",
  NLD: "Nizozemska",
  NOR: "Norveška",
  POL: "Poljska",
  PRT: "Portugal",
  ROU: "Rumunjska",
  SRB: "Srbija",
  SVK: "Slovačka",
  SVN: "Slovenija",
  SWE: "Švedska",
  CHE: "Švicarska",
  TUR: "Turska",
  UKR: "Ukrajina",
  USA: "Sjedinjene Američke Države",
  CAN: "Kanada",
  CHN: "Kina",
  RUS: "Rusija",
  JPN: "Japan",
  ALB: "Albanija",
};

export const OSIGURANJE_STATUS: Record<string, { label: string; color: string }> = {
  Aktivan: { label: "Aktivan", color: "bg-green-100 text-green-800" },
  "Na čekanju": { label: "Na čekanju", color: "bg-yellow-100 text-yellow-800" },
  Neaktivan: { label: "Neaktivan", color: "bg-red-100 text-red-800" },
  Preminuo: { label: "Preminuo", color: "bg-gray-200 text-gray-600 line-through" },
  "Nije pronađen": { label: "Nije pronađen", color: "bg-gray-100 text-gray-800" },
};

// --- MKB-10 / ICD-10 Chapter Filters (official WHO, 22 chapters) ---

export const ICD_CHAPTERS: { label: string; prefix: string }[] = [
  { label: "Sve dijagnoze", prefix: "" },
  { label: "I. A00-B99 Infekcijske i parazitske bolesti", prefix: "A,B" },
  { label: "II. C00-D48 Neoplazme", prefix: "C,D0,D1,D2,D3,D4" },
  { label: "III. D50-D89 Bolesti krvi i imunološkog sustava", prefix: "D5,D6,D7,D8" },
  { label: "IV. E00-E90 Endokrine i metaboličke bolesti", prefix: "E" },
  { label: "V. F00-F99 Mentalni poremećaji", prefix: "F" },
  { label: "VI. G00-G99 Bolesti živčanog sustava", prefix: "G" },
  { label: "VII. H00-H59 Bolesti oka", prefix: "H0,H1,H2,H3,H4,H5" },
  { label: "VIII. H60-H95 Bolesti uha", prefix: "H6,H7,H8,H9" },
  { label: "IX. I00-I99 Bolesti cirkulacijskog sustava", prefix: "I" },
  { label: "X. J00-J99 Bolesti dišnog sustava", prefix: "J" },
  { label: "XI. K00-K93 Bolesti probavnog sustava", prefix: "K" },
  { label: "XII. L00-L99 Bolesti kože", prefix: "L" },
  { label: "XIII. M00-M99 Bolesti mišićno-koštanog sustava", prefix: "M" },
  { label: "XIV. N00-N99 Bolesti genitalno-urinarnog sustava", prefix: "N" },
  { label: "XV. O00-O99 Trudnoća i porođaj", prefix: "O" },
  { label: "XVI. P00-P96 Stanja porođajnog perioda", prefix: "P" },
  { label: "XVII. Q00-Q99 Prirođene malformacije", prefix: "Q" },
  { label: "XVIII. R00-R99 Simptomi i znakovi", prefix: "R" },
  { label: "XIX. S00-T98 Ozljede i trovanja", prefix: "S,T" },
  { label: "XX. V01-Y98 Vanjski uzroci", prefix: "V,W,X,Y" },
  { label: "XXI. Z00-Z99 Čimbenici zdravstvenog statusa", prefix: "Z" },
  { label: "XXII. U00-U99 Posebne svrhe", prefix: "U" },
];

// --- Record Sensitivity ---

export const RECORD_SENSITIVITY: Record<string, string> = {
  standard: "Standardno",
  nursing: "Sestrinska dokumentacija",
  restricted: "Ograničeno",
};

export const RECORD_SENSITIVITY_OPTIONS = Object.entries(RECORD_SENSITIVITY).map(
  ([value, label]) => ({ value, label })
);

export const RECORD_SENSITIVITY_COLORS: Record<string, string> = {
  standard: "bg-gray-100 text-gray-800",
  nursing: "bg-blue-100 text-blue-800",
  restricted: "bg-red-100 text-red-800",
};

// --- CEZIH Activity ---

export const CEZIH_ACTION_LABELS: Record<string, string> = {
  insurance_check: "Provjera osiguranja",
  e_nalaz_send: "Slanje e-Nalaza",
  e_recept_send: "Slanje e-Recepta",
  e_recept_cancel: "Storno e-Recepta",
  case_create: "Kreiranje slučaja",
  case_retrieve: "Dohvat slučajeva",
  case_update: "Ažuriranje slučaja",
  case_remission: "Remisija slučaja",
  case_relapse: "Relaps slučaja",
  case_resolve: "Zatvaranje slučaja",
  case_reopen: "Ponovno otvaranje slučaja",
  case_delete: "Brisanje slučaja",
  visit_create: "Kreiranje posjete",
  visit_update: "Ažuriranje posjete",
  visit_close: "Zatvaranje posjete",
  visit_reopen: "Ponovno otvaranje posjete",
  visit_storno: "Storno posjete",
  visit_list: "Dohvat posjeta",
  foreigner_register: "Registracija stranca",
  foreigner_registration: "Registracija stranca",
  oid_generate: "OID generiranje",
  code_system_query: "Pretraga šifrarnika",
  value_set_expand: "Pretraga skupova pojmova",
  organization_search: "Pretraga organizacija",
  practitioner_search: "Pretraga djelatnika",
  document_search: "Pretraga dokumenata",
  document_replace: "Zamjena dokumenta",
  document_cancel: "Storno dokumenta",
  document_retrieve: "Dohvat dokumenta",
  sign_document: "Potpisivanje dokumenta",
  e_nalaz_cancel: "Storno e-Nalaza",
  e_nalaz_replace: "Zamjena e-Nalaza",
  patient_read: "Pregled kartona pacijenta",
  medical_record_read: "Pregled medicinskog zapisa",
  emergency_access: "Hitni pristup",
  card_removal_session_revoked: "Sesija prekinuta (kartica uklonjena)",
};

export const CEZIH_ACTION_COLORS: Record<string, string> = {
  insurance_check: "bg-blue-100 text-blue-800 border-blue-200",
  e_nalaz_send: "bg-green-100 text-green-800 border-green-200",
  e_recept_send: "bg-orange-100 text-orange-800 border-orange-200",
  e_recept_cancel: "bg-red-100 text-red-800 border-red-200",
  case_create: "bg-indigo-100 text-indigo-800 border-indigo-200",
  case_retrieve: "bg-indigo-100 text-indigo-800 border-indigo-200",
  case_update: "bg-indigo-100 text-indigo-800 border-indigo-200",
  case_remission: "bg-indigo-100 text-indigo-800 border-indigo-200",
  case_relapse: "bg-indigo-100 text-indigo-800 border-indigo-200",
  case_resolve: "bg-indigo-100 text-indigo-800 border-indigo-200",
  case_reopen: "bg-indigo-100 text-indigo-800 border-indigo-200",
  case_delete: "bg-red-100 text-red-800 border-red-200",
  visit_create: "bg-teal-100 text-teal-800 border-teal-200",
  visit_update: "bg-teal-100 text-teal-800 border-teal-200",
  visit_close: "bg-teal-100 text-teal-800 border-teal-200",
  visit_reopen: "bg-teal-100 text-teal-800 border-teal-200",
  visit_storno: "bg-red-100 text-red-800 border-red-200",
  visit_list: "bg-teal-100 text-teal-800 border-teal-200",
  foreigner_register: "bg-amber-100 text-amber-800 border-amber-200",
  foreigner_registration: "bg-amber-100 text-amber-800 border-amber-200",
  document_cancel: "bg-red-100 text-red-800 border-red-200",
  document_replace: "bg-amber-100 text-amber-800 border-amber-200",
  document_retrieve: "bg-blue-100 text-blue-800 border-blue-200",
  sign_document: "bg-green-100 text-green-800 border-green-200",
  e_nalaz_cancel: "bg-red-100 text-red-800 border-red-200",
  e_nalaz_replace: "bg-amber-100 text-amber-800 border-amber-200",
};

// --- Navigation ---

import {
  Home,
  Users,
  CalendarDays,
  FileText,
  Shield,
  Send,
  Settings,
  type LucideIcon,
} from "lucide-react";
import type { Permissions } from "@/lib/hooks/use-permissions";

export const NAV_ITEMS: {
  href: string;
  label: string;
  icon: LucideIcon;
  perm?: keyof Permissions;
}[] = [
  { href: "/dashboard", label: "Početna", icon: Home },
  { href: "/pacijenti", label: "Pacijenti", icon: Users },
  { href: "/termini", label: "Termini", icon: CalendarDays },
  { href: "/postupci", label: "Postupci", icon: FileText },
  { href: "/cezih-nalazi", label: "Slanje e-Nalaza", icon: Send, perm: "canPerformCezihOps" },
  { href: "/cezih?tab=postavke", label: "CEZIH Postavke", icon: Shield, perm: "canViewCezih" },
  { href: "/postavke", label: "Postavke", icon: Settings, perm: "canViewSettings" },
];

// --- Documents ---

export const DOCUMENT_KATEGORIJA: Record<string, string> = {
  nalaz: "Nalaz",
  snimka: "Snimka",
  dokument: "Dokument",
  ostalo: "Ostalo",
};

export const DOCUMENT_KATEGORIJA_OPTIONS = Object.entries(DOCUMENT_KATEGORIJA).map(
  ([value, label]) => ({ value, label })
);

export const DOCUMENT_KATEGORIJA_COLORS: Record<string, string> = {
  nalaz: "bg-blue-100 text-blue-800",
  snimka: "bg-purple-100 text-purple-800",
  dokument: "bg-green-100 text-green-800",
  ostalo: "bg-gray-100 text-gray-800",
};
