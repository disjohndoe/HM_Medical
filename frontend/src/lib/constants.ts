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

export const WORKING_HOURS_START = 8;
export const WORKING_HOURS_END = 20;
export const SLOT_GRANULARITY = 15;

export const DURATION_OPTIONS = [15, 30, 45, 60, 90, 120] as const;

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
export const CEZIH_MANDATORY_TYPES = new Set([
  "ambulantno_izvjesce",
  "specijalisticki_nalaz",
  "otpusno_pismo",
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

export const OSIGURANJE_STATUS: Record<string, { label: string; color: string }> = {
  Aktivan: { label: "Aktivan", color: "bg-green-100 text-green-800" },
  "Na čekanju": { label: "Na čekanju", color: "bg-yellow-100 text-yellow-800" },
  Neaktivan: { label: "Neaktivan", color: "bg-red-100 text-red-800" },
};

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
  foreigner_register: "Registracija stranca",
  oid_lookup: "OID pretraga",
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
  foreigner_register: "bg-amber-100 text-amber-800 border-amber-200",
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
  { href: "/cezih-nalazi", label: "CEZIH Nalazi", icon: Send, perm: "canPerformCezihOps" },
  { href: "/cezih", label: "CEZIH Postavke", icon: Shield, perm: "canViewCezih" },
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
