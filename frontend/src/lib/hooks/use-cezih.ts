import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api-client"
import type {
  CaseActionResponse,
  CaseItem,
  CaseResponse,
  CasesListResponse,
  CezihActivityListResponse,
  CezihDashboardStats,
  CezihPatientImport,
  CezihStatusResponse,
  CodeSystemItem,
  CreateCaseRequest,
  DocumentActionResponse,
  DocumentSearchItem,
  ENalazResponse,
  EReceptResponse,
  EReceptStornoResponse,
  ForeignerRegistrationRequest,
  ForeignerRegistrationResponse,
  PatientIdentifierSearchResponse,
  InsuranceCheckResponse,
  LijekItem,
  OidGenerateResponse,
  OrganizationItem,
  PatientCezihSummary,
  CreateVisitRequest,
  PractitionerItem,
  ValueSetExpandResponse,
  VisitItem,
  VisitResponse,
  VisitsListResponse,
} from "@/lib/types"

export function useCezihStatus() {
  return useQuery({
    queryKey: ["cezih", "status"],
    queryFn: () => api.get<CezihStatusResponse>("/cezih/status"),
    refetchInterval: 5_000,
    staleTime: 3_000,
  })
}

/**
 * Single source of truth for CEZIH connection status display.
 * Returns 3 separate indicator states (agent, card, VPN) plus legacy
 * single-dot fields for sidebar/dashboard backward compatibility.
 */
export function useCezihConnectionDisplay() {
  const { data, isLoading, isError, error } = useCezihStatus()

  const agentConnected = data?.agent_connected === true
  const cardInserted = data?.card_inserted === true
  const vpnConnected = data?.vpn_connected === true
  const readerAvailable = data?.reader_available === true

  // Agent indicator
  const agent = agentConnected
    ? { dotClass: "bg-green-500", label: "Agent povezan" }
    : { dotClass: "bg-muted-foreground/50", label: "Agent nije povezan" }

  // Card indicator — gray when agent not connected (status unknown)
  let card: { dotClass: string; label: string; detail: string | null }
  if (!agentConnected) {
    card = { dotClass: "bg-muted-foreground/30", label: "Kartica — čeka agent", detail: null }
  } else if (!readerAvailable) {
    card = { dotClass: "bg-muted-foreground/30", label: "Čitač nije pronađen", detail: null }
  } else if (cardInserted) {
    card = { dotClass: "bg-green-500", label: "Kartica umetnuta", detail: data?.card_holder ?? null }
  } else {
    card = { dotClass: "bg-red-500", label: "Umetnite karticu", detail: null }
  }

  // VPN indicator — gray when agent not connected (status unknown)
  const vpn = !agentConnected
    ? { dotClass: "bg-muted-foreground/30", label: "VPN — čeka agent" }
    : vpnConnected
      ? { dotClass: "bg-green-500", label: "VPN spojen" }
      : { dotClass: "bg-red-500", label: "VPN nije spojen" }

  // Legacy single dot for sidebar/dashboard
  let dotColor = "bg-muted-foreground/50"
  let label = "Nije povezano"
  if (agentConnected && cardInserted && vpnConnected) {
    dotColor = "bg-green-500"
    label = "CEZIH spreman"
  } else if (agentConnected && !cardInserted) {
    dotColor = "bg-yellow-500"
    label = "Umetnite karticu"
  } else if (agentConnected) {
    dotColor = "bg-yellow-500"
    label = "Djelomično povezano"
  }

  const isConnected = agentConnected && cardInserted && vpnConnected

  return {
    isLoading,
    isError,
    error,
    isConnected,
    dotColor,
    label,
    agent,
    card,
    vpn,
    connectedDoctor: agentConnected && cardInserted ? (data?.connected_doctor ?? null) : null,
    connectedClinic: agentConnected && cardInserted ? (data?.connected_clinic ?? null) : null,
    raw: data,
  }
}

export function useInsuranceCheck() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (patientId: string) =>
      api.post<InsuranceCheckResponse>("/cezih/provjera-osiguranja", { patient_id: patientId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cezih", "activity"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "dashboard-stats"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "patient"], exact: false })
      queryClient.invalidateQueries({ queryKey: ["patients"] })
    },
  })
}

/** Ad-hoc MBO-only insurance check (standalone CEZIH tab card). */
export function useInsuranceCheckByMbo() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (mbo: string) =>
      api.post<InsuranceCheckResponse>("/cezih/provjera-osiguranja", { mbo }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cezih", "activity"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "dashboard-stats"] })
    },
  })
}

export function useSendENalaz() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      patient_id,
      record_id,
      encounter_id,
      case_id,
    }: {
      patient_id: string
      record_id: string
      encounter_id?: string
      case_id?: string
    }) =>
      api.post<ENalazResponse>("/cezih/e-nalaz", {
        patient_id,
        record_id,
        encounter_id: encounter_id || "",
        case_id: case_id || "",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["medical-records"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "activity"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "dashboard-stats"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "patient"], exact: false })
    },
  })
}

export function useSendERecept() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ patient_id, lijekovi }: { patient_id: string; lijekovi: { atk: string; naziv: string; kolicina: number; doziranje: string; napomena: string }[] }) =>
      api.post<EReceptResponse>("/cezih/e-recept", { patient_id, lijekovi }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cezih", "activity"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "dashboard-stats"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "patient"], exact: false })
    },
  })
}

export function useCancelERecept() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (receptId: string) =>
      api.delete<EReceptStornoResponse>(`/cezih/e-recept/${receptId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cezih", "patient"], exact: false })
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
    },
  })
}

// --- Feature 1: Activity Log ---

export function useCezihActivity(skip = 0, limit = 20) {
  return useQuery({
    queryKey: ["cezih", "activity", skip, limit],
    queryFn: () =>
      api.get<CezihActivityListResponse>(`/cezih/activity?skip=${skip}&limit=${limit}`),
  })
}

// --- Feature 2: Patient CEZIH Summary ---

export function usePatientCezihSummary(patientId: string) {
  return useQuery({
    queryKey: ["cezih", "patient", patientId],
    queryFn: () =>
      api.get<PatientCezihSummary>(`/cezih/patient/${patientId}/summary`),
    enabled: !!patientId,
  })
}

// --- Feature 3: Dashboard Stats ---

export function useCezihDashboardStats() {
  return useQuery({
    queryKey: ["cezih", "dashboard-stats"],
    queryFn: () => api.get<CezihDashboardStats>("/cezih/dashboard-stats"),
  })
}

/** Sidebar badge — mutation invalidation + 60s polling so cross-tab / multi-user
 *  changes surface without navigation. Pauses when tab is hidden. */
export function useCezihNalaziCount() {
  return useQuery({
    queryKey: ["cezih", "dashboard-stats"],
    queryFn: () => api.get<CezihDashboardStats>("/cezih/dashboard-stats"),
    select: (data) => data.neposlani_nalazi ?? 0,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    staleTime: 30_000,
  })
}

// --- Feature 4: Drug Search ---

export function useDrugSearch(query: string) {
  return useQuery({
    queryKey: ["cezih", "lijekovi", query],
    queryFn: () =>
      api.get<LijekItem[]>(`/cezih/lijekovi?q=${encodeURIComponent(query)}`),
    enabled: query.length >= 2,
  })
}


// ============================================================
// TC6: OID Registry Lookup
// ============================================================

export function useOidGenerate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      api.post<OidGenerateResponse>("/cezih/oid-generate", { quantity: 1 }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cezih", "activity"] }),
  })
}


// ============================================================
// TC7: Code System Query
// ============================================================

export function useCodeSystemQuery(system: string, query: string, enableEmpty = false) {
  return useQuery({
    queryKey: ["cezih", "code-system", system, query],
    queryFn: () =>
      api.get<CodeSystemItem[]>(`/cezih/code-system?system=${encodeURIComponent(system)}&q=${encodeURIComponent(query)}`),
    enabled: enableEmpty ? system.length >= 1 : query.length >= 1,
  })
}


export function useIcd10Search(query: string, limit = 20) {
  return useQuery({
    queryKey: ["icd10", "search", query],
    queryFn: () =>
      api.get<CodeSystemItem[]>(`/cezih/icd10/search?q=${encodeURIComponent(query)}&limit=${limit}`),
    enabled: query.length >= 2,
  })
}


// ============================================================
// TC8: Value Set Expand
// ============================================================

export function useValueSetExpand(url: string, filter?: string) {
  return useQuery({
    queryKey: ["cezih", "value-set", url, filter],
    queryFn: () => {
      const params = new URLSearchParams({ url })
      if (filter) params.set("filter", filter)
      return api.get<ValueSetExpandResponse>(`/cezih/value-set?${params}`)
    },
    enabled: !!url,
  })
}


// ============================================================
// TC9: Subject Registry (mCSD)
// ============================================================

export function useOrganizationSearch(name: string) {
  return useQuery({
    queryKey: ["cezih", "organizations", name],
    queryFn: () =>
      api.get<OrganizationItem[]>(`/cezih/organizations?name=${encodeURIComponent(name)}`),
    enabled: name.length >= 2,
  })
}

export function usePractitionerSearch(name: string) {
  return useQuery({
    queryKey: ["cezih", "practitioners", name],
    queryFn: () =>
      api.get<PractitionerItem[]>(`/cezih/practitioners?name=${encodeURIComponent(name)}`),
    enabled: name.length >= 2,
  })
}


// ============================================================
// TC11: Foreigner Registration
// ============================================================

export function useRegisterForeigner() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ForeignerRegistrationRequest) =>
      api.post<ForeignerRegistrationResponse>("/cezih/patients/foreigner", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
      qc.invalidateQueries({ queryKey: ["cezih", "patients", "search"] })
    },
  })
}

export function useForeignerSearch(system: string, value: string) {
  return useQuery({
    queryKey: ["cezih", "patients", "search", system, value],
    queryFn: () =>
      api.get<PatientIdentifierSearchResponse>(
        `/cezih/patients/search?system=${encodeURIComponent(system)}&value=${encodeURIComponent(value)}`
      ),
    enabled: system !== "mbo" && value.length >= 5,
    retry: false,
  })
}


// ============================================================
// TC12-14: Visit Management
// ============================================================

export function useListVisits(patientId: string) {
  return useQuery({
    queryKey: ["cezih", "visits", patientId],
    queryFn: () =>
      api.get<VisitsListResponse>(`/cezih/visits?patient_id=${encodeURIComponent(patientId)}`),
    enabled: !!patientId,
  })
}

export function useCreateVisit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateVisitRequest) =>
      api.post<VisitResponse>("/cezih/visits", data),
    onSuccess: (resp, vars) => {
      // CEZIH QEDm (read) is eventually consistent with the write side — the
      // new visit is usually not visible in GET /cezih/visits for several
      // seconds. Insert optimistically so the Posjete table sees it right
      // away. Do NOT invalidate ["cezih","visits"] — that would trigger a
      // refetch that blows away the optimistic row before CEZIH catches up.
      const queryKey = ["cezih", "visits", vars.patient_id]
      const newVisit: VisitItem = {
        visit_id: resp.visit_id,
        patient_mbo: vars.patient_id,
        status: resp.status || "in-progress",
        visit_type: resp.nacin_prijema || vars.nacin_prijema || "6",
        visit_type_display: null,
        vrsta_posjete: resp.vrsta_posjete || vars.vrsta_posjete || "1",
        vrsta_posjete_display: "",
        tip_posjete: resp.tip_posjete || vars.tip_posjete || "2",
        tip_posjete_display: "",
        reason: vars.reason || null,
        period_start: new Date().toISOString(),
        period_end: null,
        service_provider_code: null, // null → isExternalVisit() is false → shows as "Naša"
        practitioner_id: null,
        practitioner_ids: [],
        diagnosis_case_ids: [],
        _local: true,
      }
      qc.setQueryData<VisitsListResponse>(queryKey, (old) => {
        if (!old) return { visits: [newVisit] }
        if (old.visits.some((v) => v.visit_id === newVisit.visit_id)) return old
        return { visits: [newVisit, ...old.visits] }
      })
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
      qc.invalidateQueries({ queryKey: ["cezih", "dashboard-stats"] })
    },
  })
}

export function useUpdateVisit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ visitId, reason, nacin_prijema, vrsta_posjete, tip_posjete,
      diagnosis_case_id, additional_practitioner_id, period_start, patientId }: {
      visitId: string; reason?: string; nacin_prijema?: string;
      vrsta_posjete?: string; tip_posjete?: string;
      diagnosis_case_id?: string; additional_practitioner_id?: string;
      period_start?: string; patientId: string
    }) =>
      api.patch<VisitResponse>(`/cezih/visits/${visitId}?patient_id=${encodeURIComponent(patientId)}`, {
        reason, nacin_prijema, vrsta_posjete, tip_posjete,
        diagnosis_case_id, additional_practitioner_id, period_start,
      }),
    onSuccess: (_resp, vars) => {
      // Optimistic merge — see useCreateVisit comment.
      const queryKey = ["cezih", "visits", vars.patientId]
      qc.setQueryData<VisitsListResponse>(queryKey, (old) => {
        if (!old) return old
        return {
          visits: old.visits.map((v) =>
            v.visit_id !== vars.visitId
              ? v
              : {
                  ...v,
                  ...(vars.reason !== undefined && { reason: vars.reason || null }),
                  ...(vars.nacin_prijema !== undefined && {
                    visit_type: vars.nacin_prijema,
                    visit_type_display: null,
                  }),
                  ...(vars.vrsta_posjete !== undefined && {
                    vrsta_posjete: vars.vrsta_posjete,
                    vrsta_posjete_display: "",
                  }),
                  ...(vars.tip_posjete !== undefined && {
                    tip_posjete: vars.tip_posjete,
                    tip_posjete_display: "",
                  }),
                  ...(vars.diagnosis_case_id !== undefined && {
                    diagnosis_case_ids: vars.diagnosis_case_id ? [vars.diagnosis_case_id] : [],
                  }),
                  ...(vars.period_start !== undefined && { period_start: vars.period_start }),
                  updated_at: new Date().toISOString(),
                  _local: true,
                },
          ),
        }
      })
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
      qc.invalidateQueries({ queryKey: ["cezih", "visits", vars.patientId] })
    },
  })
}

export function useVisitAction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ visitId, action, patientId, periodStart }: { visitId: string; action: string; patientId: string; periodStart?: string | null }) =>
      api.post<VisitResponse>(`/cezih/visits/${visitId}/action?patient_id=${encodeURIComponent(patientId)}`, { action, period_start: periodStart || undefined }),
    onSuccess: (_resp, vars) => {
      // Optimistic status flip — see useCreateVisit comment.
      const queryKey = ["cezih", "visits", vars.patientId]
      const newStatus =
        vars.action === "close" ? "finished"
        : vars.action === "reopen" ? "in-progress"
        : vars.action === "storno" ? "entered-in-error"
        : null
      if (newStatus) {
        const nowIso = new Date().toISOString()
        qc.setQueryData<VisitsListResponse>(queryKey, (old) => {
          if (!old) return old
          return {
            visits: old.visits.map((v) =>
              v.visit_id !== vars.visitId
                ? v
                : {
                    ...v,
                    status: newStatus,
                    period_end:
                      vars.action === "close" ? nowIso
                      : vars.action === "reopen" ? null
                      : v.period_end,
                    updated_at: nowIso,
                    _local: true,
                  },
            ),
          }
        })
      }
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
      qc.invalidateQueries({ queryKey: ["cezih", "visits", vars.patientId] })
    },
  })
}


// ============================================================
// TC15-17: Case Management
// ============================================================

export function useRetrieveCases(patientId: string) {
  return useQuery({
    queryKey: ["cezih", "cases", patientId],
    queryFn: () =>
      api.get<CasesListResponse>(`/cezih/cases?patient_id=${encodeURIComponent(patientId)}`),
    enabled: !!patientId,
  })
}

export function useCreateCase() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateCaseRequest) =>
      api.post<CaseResponse>("/cezih/cases", data),
    onSuccess: (resp, vars) => {
      // CEZIH's /health-issue-services (write) and /ihe-qedm-services (read) are
      // eventually consistent — a newly-created case is usually not yet visible
      // via QEDm GET /Condition for several seconds. Insert optimistically so
      // the table + e-Nalaz case dropdown see it immediately.
      const queryKey = ["cezih", "cases", vars.patient_id]
      const newCase: CaseItem = {
        case_id: resp.cezih_case_id || resp.local_case_id,
        icd_code: vars.icd_code,
        icd_display: vars.icd_display,
        clinical_status: "active",
        verification_status: vars.verification_status ?? null,
        onset_date: vars.onset_date,
        abatement_date: null,
        note: vars.note ?? null,
        _local: true,
      }
      qc.setQueryData<CasesListResponse>(queryKey, (old) => {
        if (!old) return { cases: [newCase] }
        if (old.cases.some((c) => c.case_id === newCase.case_id)) return old
        return { cases: [newCase, ...old.cases] }
      })
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
      qc.invalidateQueries({ queryKey: ["cezih", "dashboard-stats"] })
    },
  })
}

// Status-transition actions → target clinical_status in our local view.
// (Invariant: a case NEVER disappears from the Slučajevi table — we always
// keep it visible, just with the new status. CEZIH QEDm's eventual
// consistency would otherwise hide the case for several seconds after any
// action, which the user experiences as "my case vanished".)
const CASE_ACTION_TO_STATUS: Record<string, string> = {
  resolve: "resolved",
  remission: "remission",
  relapse: "relapse",
  reopen: "active",
}

export function useUpdateCaseStatus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ caseId, patientId, action }: { caseId: string; patientId: string; action: string }) =>
      api.put<CaseActionResponse>(`/cezih/cases/${caseId}/status?patient_id=${encodeURIComponent(patientId)}`, { action }),
    onSuccess: (resp, vars) => {
      const queryKey = ["cezih", "cases", vars.patientId]
      qc.setQueryData<CasesListResponse>(queryKey, (old) => {
        if (!old) return old
        if (vars.action === "create_recurring") {
          // 2.2 Ponavljajući spawns a new case inheriting the parent's ICD.
          const parent = old.cases.find((c) => c.case_id === vars.caseId)
          if (!parent) return old
          const newCaseId = resp.case_id || `pending-${vars.caseId}-rec`
          if (old.cases.some((c) => c.case_id === newCaseId)) return old
          const today = new Date().toISOString().split("T")[0]
          const newCase: CaseItem = {
            case_id: newCaseId,
            icd_code: parent.icd_code,
            icd_display: parent.icd_display,
            clinical_status: "recurrence",
            verification_status: parent.verification_status,
            onset_date: today,
            abatement_date: null,
            note: null,
            _local: true,
          }
          return { cases: [newCase, ...old.cases] }
        }
        const newStatus = CASE_ACTION_TO_STATUS[vars.action]
        if (!newStatus) return old
        const today = new Date().toISOString().split("T")[0]
        return {
          cases: old.cases.map((c) =>
            c.case_id !== vars.caseId
              ? c
              : {
                  ...c,
                  clinical_status: newStatus,
                  abatement_date: newStatus === "resolved" ? today : c.abatement_date,
                },
          ),
        }
      })
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
    },
  })
}

export function useUpdateCaseData() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ caseId, patientId, ...data }: {
      caseId: string; patientId: string;
      current_clinical_status?: string; verification_status?: string;
      icd_code?: string; icd_display?: string;
      onset_date?: string; abatement_date?: string; note?: string;
    }) =>
      api.put<CaseActionResponse>(`/cezih/cases/${caseId}/data?patient_id=${encodeURIComponent(patientId)}`, data),
    onSuccess: (_resp, vars) => {
      const queryKey = ["cezih", "cases", vars.patientId]
      qc.setQueryData<CasesListResponse>(queryKey, (old) => {
        if (!old) return old
        return {
          cases: old.cases.map((c) =>
            c.case_id !== vars.caseId
              ? c
              : {
                  ...c,
                  ...(vars.verification_status !== undefined && { verification_status: vars.verification_status }),
                  ...(vars.icd_code !== undefined && { icd_code: vars.icd_code }),
                  ...(vars.icd_display !== undefined && { icd_display: vars.icd_display }),
                  ...(vars.onset_date !== undefined && { onset_date: vars.onset_date }),
                  ...(vars.abatement_date !== undefined && { abatement_date: vars.abatement_date || null }),
                  ...(vars.note !== undefined && { note: vars.note || null }),
                },
          ),
        }
      })
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
    },
  })
}


// ============================================================
// TC19-22: Document Operations
// ============================================================

export function useDocumentSearch(params: {
  patient_id?: string; type?: string; date_from?: string; date_to?: string; status?: string;
}) {
  const searchParams = new URLSearchParams()
  if (params.patient_id) searchParams.set("patient_id", params.patient_id)
  if (params.type) searchParams.set("type", params.type)
  if (params.date_from) searchParams.set("date_from", params.date_from)
  if (params.date_to) searchParams.set("date_to", params.date_to)
  if (params.status) searchParams.set("status", params.status)
  const qs = searchParams.toString()

  return useQuery({
    queryKey: ["cezih", "documents", params],
    queryFn: () =>
      api.get<DocumentSearchItem[]>(`/cezih/documents${qs ? `?${qs}` : ""}`),
    enabled: !!(params.patient_id || params.type),
  })
}

export function useReplaceDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ referenceId, record_id }: { referenceId: string; record_id?: string }) =>
      api.put<DocumentActionResponse>(`/cezih/e-nalaz/${referenceId}`, record_id ? { record_id } : {}),
    onSuccess: (_resp, vars) => {
      // CEZIH MHD (read) is eventually consistent with replace. Mark the
      // replaced row as "Zatvorena" (superseded) optimistically so the user
      // sees the status change right away. A new "current" row for the
      // replacement will appear on the next natural refetch of the search.
      // Do NOT invalidate ["cezih","documents"] — would wipe this flip.
      qc.setQueriesData<DocumentSearchItem[]>(
        { queryKey: ["cezih", "documents"], exact: false },
        (old) => {
          if (!old) return old
          return old.map((d) =>
            d.id === vars.referenceId ? { ...d, status: "Zatvorena", _local: true } : d,
          )
        },
      )
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
      qc.invalidateQueries({ queryKey: ["cezih", "patient"], exact: false })
      qc.invalidateQueries({ queryKey: ["medical-records"] })
    },
  })
}

export function useCancelDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (referenceId: string) =>
      api.delete<DocumentActionResponse>(`/cezih/e-nalaz/${referenceId}`),
    onSuccess: (_resp, referenceId) => {
      // CEZIH MHD eventually-consistent — optimistic status flip to
      // "Pogreška" (entered-in-error) so the user sees immediate feedback.
      qc.setQueriesData<DocumentSearchItem[]>(
        { queryKey: ["cezih", "documents"], exact: false },
        (old) => {
          if (!old) return old
          return old.map((d) =>
            d.id === referenceId ? { ...d, status: "Pogreška", _local: true } : d,
          )
        },
      )
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
      qc.invalidateQueries({ queryKey: ["cezih", "patient"], exact: false })
      qc.invalidateQueries({ queryKey: ["medical-records"] })
    },
  })
}

export function useRetrieveDocument() {
  return useMutation({
    mutationFn: async ({ id, contentUrl }: { id: string; contentUrl?: string }) => {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api"
      const url = contentUrl
        ? `${API_BASE}/cezih/e-nalaz/${id}/document?url=${encodeURIComponent(contentUrl)}`
        : `${API_BASE}/cezih/e-nalaz/${id}/document`
      const response = await fetch(url, { credentials: "include" })
      if (!response.ok) throw new Error("Failed to retrieve document")
      return response.blob()
    },
  })
}

export function useImportPatientFromCezih() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (mbo: string) =>
      api.post<CezihPatientImport>("/cezih/import-patient", { mbo }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["patients"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "activity"] })
    },
  })
}
