import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api, CezihApiError, isSigningError } from "@/lib/api-client"
import { clearError, setError } from "@/lib/hooks/use-cezih-error-state"
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

function showCezihErrorToast(err: Error) {
  if (err instanceof CezihApiError && err.cezih_error) {
    toast.error("Greška na CEZIH-u. Pokušajte ponovno za nekoliko minuta.", {
      duration: 10_000,
    })
  } else if (isSigningError(err.message)) {
    toast.error(err.message, {
      action: {
        label: "Idi na Postavke",
        onClick: () => (window.location.href = "/postavke/korisnici"),
      },
    })
  } else {
    toast.error(err.message)
  }
}

/** Extract code + diagnostics from an error for row-bound setError calls. */
function cezihErrorParts(err: Error): { code?: string; diagnostics?: string } {
  if (err instanceof CezihApiError && err.cezih_error) {
    return { code: err.cezih_error.code, diagnostics: err.cezih_error.diagnostics }
  }
  return {}
}

export function useCezihStatus() {
  return useQuery({
    queryKey: ["cezih", "status"],
    queryFn: () => api.get<CezihStatusResponse>("/cezih/status"),
    refetchInterval: 5_000,
    refetchIntervalInBackground: false,
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
    onError: (err) => toast.error(err.message),
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
    onError: (err) => toast.error(err.message),
  })
}

export type AdhocIdentifierType = "mbo" | "ehic" | "putovnica"

/** Ad-hoc insurance check by any CEZIH identifier type (MBO, EHIC, passport). */
export function useInsuranceCheckByIdentifier() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      identifier_type,
      identifier_value,
    }: {
      identifier_type: AdhocIdentifierType
      identifier_value: string
    }) =>
      api.post<InsuranceCheckResponse>("/cezih/provjera-osiguranja", {
        identifier_type,
        identifier_value,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cezih", "activity"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "dashboard-stats"] })
    },
    onError: (err) => toast.error(err.message),
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
    onSuccess: (_resp, vars) => {
      clearError(vars.record_id)
      queryClient.invalidateQueries({ queryKey: ["medical-records"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "activity"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "dashboard-stats"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "patient"], exact: false })
    },
    onError: (err, vars) => {
      showCezihErrorToast(err)
      setError(vars.record_id, err.message, cezihErrorParts(err).code, cezihErrorParts(err).diagnostics)
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
    onError: (err) => toast.error(err.message),
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
    onError: (err) => toast.error(err.message),
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
    onError: (err) => toast.error(err.message),
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
    onError: (err) => showCezihErrorToast(err),
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
    retry: 1,
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
    onMutate: async (vars) => {
      await qc.cancelQueries({ queryKey: ["cezih", "visits", vars.patient_id] })
      const queryKey = ["cezih", "visits", vars.patient_id]
      const prev = qc.getQueryData<VisitsListResponse>(queryKey)
      const tempId = `temp-${Date.now()}`
      const newVisit: VisitItem = {
        visit_id: tempId,
        patient_mbo: vars.patient_id,
        status: "in-progress",
        visit_type: vars.nacin_prijema || "6",
        visit_type_display: null,
        vrsta_posjete: vars.vrsta_posjete || "1",
        vrsta_posjete_display: null,
        tip_posjete: vars.tip_posjete || "1",
        tip_posjete_display: null,
        reason: vars.reason || null,
        period_start: new Date().toISOString(),
        period_end: null,
        service_provider_code: null,
        practitioner_id: null,
        practitioner_ids: [],
        diagnosis_case_ids: [],
        _local: true,
      }
      qc.setQueryData<VisitsListResponse>(queryKey, (old) => {
        if (!old) return { visits: [newVisit] }
        return { visits: [newVisit, ...old.visits] }
      })
      return { prev, tempId, queryKey }
    },
    onSuccess: (resp, vars, ctx) => {
      if (ctx) {
        clearError(ctx.tempId)
        if (resp.visit_id) clearError(resp.visit_id)
      }
      // Replace temp ID with real one from CEZIH
      if (ctx) {
        qc.setQueryData<VisitsListResponse>(ctx.queryKey, (old) => {
          if (!old) return old
          return {
            visits: old.visits.map((v) =>
              v.visit_id === ctx.tempId
                ? {
                    ...v,
                    visit_id: resp.visit_id,
                    visit_type: resp.nacin_prijema || v.visit_type,
                    vrsta_posjete: resp.vrsta_posjete || v.vrsta_posjete,
                    tip_posjete: resp.tip_posjete || v.tip_posjete,
                    status: resp.status || v.status,
                  }
                : v,
            ),
          }
        })
      }
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
      qc.invalidateQueries({ queryKey: ["cezih", "dashboard-stats"] })
    },
    onError: (err, vars, ctx) => {
      showCezihErrorToast(err)
      if (ctx) {
        setError(ctx.tempId, err.message, cezihErrorParts(err).code, cezihErrorParts(err).diagnostics)
        qc.setQueryData(ctx.queryKey, ctx.prev)
      }
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
    onMutate: async (vars) => {
      const queryKey = ["cezih", "visits", vars.patientId]
      await qc.cancelQueries({ queryKey })
      const prev = qc.getQueryData<VisitsListResponse>(queryKey)
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
                    vrsta_posjete_display: null,
                  }),
                  ...(vars.tip_posjete !== undefined && {
                    tip_posjete: vars.tip_posjete,
                    tip_posjete_display: null,
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
      return { prev, queryKey }
    },
    onSuccess: (_resp, vars) => {
      clearError(vars.visitId)
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
      qc.invalidateQueries({ queryKey: ["cezih", "visits", vars.patientId] })
    },
    onError: (err, vars, ctx) => {
      showCezihErrorToast(err)
      setError(vars.visitId, err.message, cezihErrorParts(err).code, cezihErrorParts(err).diagnostics)
      if (ctx) qc.setQueryData(ctx.queryKey, ctx.prev)
    },
  })
}

export function useVisitAction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ visitId, action, patientId, periodStart }: { visitId: string; action: string; patientId: string; periodStart?: string | null }) =>
      api.post<VisitResponse>(`/cezih/visits/${visitId}/action?patient_id=${encodeURIComponent(patientId)}`, { action, period_start: periodStart || undefined }),
    onMutate: async (vars) => {
      const queryKey = ["cezih", "visits", vars.patientId]
      await qc.cancelQueries({ queryKey })
      const prev = qc.getQueryData<VisitsListResponse>(queryKey)
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
      return { prev, queryKey }
    },
    onSuccess: (_resp, vars) => {
      clearError(vars.visitId)
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
      qc.invalidateQueries({ queryKey: ["cezih", "visits", vars.patientId] })
    },
    onError: (err, vars, ctx) => {
      showCezihErrorToast(err)
      setError(vars.visitId, err.message, cezihErrorParts(err).code, cezihErrorParts(err).diagnostics)
      if (ctx) qc.setQueryData(ctx.queryKey, ctx.prev)
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
    onMutate: async (vars) => {
      const queryKey = ["cezih", "cases", vars.patient_id]
      await qc.cancelQueries({ queryKey })
      const prev = qc.getQueryData<CasesListResponse>(queryKey)
      const tempId = `temp-${Date.now()}`
      const newCase: CaseItem = {
        case_id: tempId,
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
        return { cases: [newCase, ...old.cases] }
      })
      return { prev, tempId, queryKey }
    },
    onSuccess: (resp, vars, ctx) => {
      if (ctx) {
        clearError(ctx.tempId)
        const realId = resp.cezih_case_id || resp.local_case_id
        if (realId) clearError(realId)
        qc.setQueryData<CasesListResponse>(ctx.queryKey, (old) => {
          if (!old) return old
          return {
            cases: old.cases.map((c) =>
              c.case_id === ctx.tempId
                ? { ...c, case_id: resp.cezih_case_id || resp.local_case_id }
                : c,
            ),
          }
        })
      }
      qc.invalidateQueries({ queryKey: ["cezih", "cases", vars.patient_id] })
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
      qc.invalidateQueries({ queryKey: ["cezih", "dashboard-stats"] })
    },
    onError: (err, _vars, ctx) => {
      showCezihErrorToast(err)
      if (ctx) {
        setError(ctx.tempId, err.message, cezihErrorParts(err).code, cezihErrorParts(err).diagnostics)
        qc.setQueryData(ctx.queryKey, ctx.prev)
      }
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
    onMutate: async (vars) => {
      const queryKey = ["cezih", "cases", vars.patientId]
      await qc.cancelQueries({ queryKey })
      const prev = qc.getQueryData<CasesListResponse>(queryKey)
      if (vars.action === "create_recurring") {
        // Will be handled in onSuccess with real case ID
        return { prev, queryKey }
      }
      const newStatus = CASE_ACTION_TO_STATUS[vars.action]
      if (newStatus) {
        const today = new Date().toISOString().split("T")[0]
        qc.setQueryData<CasesListResponse>(queryKey, (old) => {
          if (!old) return old
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
      }
      return { prev, queryKey }
    },
    onSuccess: (resp, vars, ctx) => {
      if (vars.action === "create_recurring" && ctx) {
        qc.setQueryData<CasesListResponse>(ctx.queryKey, (old) => {
          if (!old) return old
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
        })
      }
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
    },
    onError: (err, vars, ctx) => {
      showCezihErrorToast(err)
      setError(vars.caseId, err.message, cezihErrorParts(err).code, cezihErrorParts(err).diagnostics)
      if (ctx) qc.setQueryData(ctx.queryKey, ctx.prev)
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
    onMutate: async (vars) => {
      const queryKey = ["cezih", "cases", vars.patientId]
      await qc.cancelQueries({ queryKey })
      const prev = qc.getQueryData<CasesListResponse>(queryKey)
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
      return { prev, queryKey }
    },
    onSuccess: (_resp, vars) => {
      clearError(vars.caseId)
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
    },
    onError: (err, vars, ctx) => {
      showCezihErrorToast(err)
      setError(vars.caseId, err.message, cezihErrorParts(err).code, cezihErrorParts(err).diagnostics)
      if (ctx) qc.setQueryData(ctx.queryKey, ctx.prev)
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

/** Atomic edit-and-replace: signs + calls CEZIH ITI-65 replace first, only
 *  applies the local record PATCH when CEZIH returns 2xx. Use this instead of
 *  the PATCH-then-replace pattern for any edit that should be mirrored to
 *  CEZIH — prevents DB/CEZIH divergence when CEZIH fails. */
export function useReplaceDocumentWithEdit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      referenceId,
      record_id,
      patient_id,
      encounter_id,
      case_id,
      datum,
      tip,
      dijagnoza_mkb,
      dijagnoza_tekst,
      sadrzaj,
      sensitivity,
      preporucena_terapija,
    }: {
      referenceId: string
      record_id: string
      patient_id: string
      encounter_id?: string
      case_id?: string
      datum?: string | null
      tip?: string | null
      dijagnoza_mkb?: string | null
      dijagnoza_tekst?: string | null
      sadrzaj?: string | null
      sensitivity?: string | null
      preporucena_terapija?: unknown[] | null
    }) =>
      api.put<DocumentActionResponse>(`/cezih/e-nalaz/${referenceId}/replace-with-edit`, {
        record_id,
        patient_id,
        encounter_id: encounter_id || "",
        case_id: case_id || "",
        datum,
        tip,
        dijagnoza_mkb,
        dijagnoza_tekst,
        sadrzaj,
        sensitivity,
        preporucena_terapija,
      }),
    onSuccess: (_resp, vars) => {
      clearError(vars.referenceId)
      clearError(vars.record_id)
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
      qc.invalidateQueries({ queryKey: ["cezih", "patient"], exact: false })
      qc.invalidateQueries({ queryKey: ["cezih", "documents"], exact: false })
      qc.invalidateQueries({ queryKey: ["medical-records"] })
    },
    onError: (err, vars) => {
      showCezihErrorToast(err)
      const parts = cezihErrorParts(err)
      setError(vars.record_id, err.message, parts.code, parts.diagnostics)
    },
  })
}

export function useReplaceDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ referenceId, record_id }: { referenceId: string; record_id?: string }) =>
      api.put<DocumentActionResponse>(`/cezih/e-nalaz/${referenceId}`, record_id ? { record_id } : {}),
    onMutate: async (vars) => {
      const queryFilter = { queryKey: ["cezih", "documents"], exact: false }
      await qc.cancelQueries(queryFilter)
      const prev = qc.getQueriesData<DocumentSearchItem[]>(queryFilter)
      qc.setQueriesData<DocumentSearchItem[]>(queryFilter, (old) => {
        if (!old) return old
        return old.map((d) =>
          d.id === vars.referenceId ? { ...d, status: "Zatvorena", _local: true } : d,
        )
      })
      return { prev }
    },
    onSuccess: (_resp, vars) => {
      clearError(vars.referenceId)
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
      qc.invalidateQueries({ queryKey: ["cezih", "patient"], exact: false })
      qc.invalidateQueries({ queryKey: ["medical-records"] })
    },
    onError: (err, vars, ctx) => {
      showCezihErrorToast(err)
      setError(vars.referenceId, err.message, cezihErrorParts(err).code, cezihErrorParts(err).diagnostics)
      if (ctx?.prev) {
        for (const [key, data] of ctx.prev) {
          qc.setQueryData(key, data)
        }
      }
    },
  })
}

export function useCancelDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (referenceId: string) =>
      api.delete<DocumentActionResponse>(`/cezih/e-nalaz/${referenceId}`),
    onSuccess: (_resp, referenceId) => {
      clearError(referenceId)
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
      qc.invalidateQueries({ queryKey: ["cezih", "patient"], exact: false })
      qc.invalidateQueries({ queryKey: ["cezih", "documents"], exact: false })
      qc.invalidateQueries({ queryKey: ["medical-records"] })
    },
    onError: (err, referenceId) => {
      showCezihErrorToast(err)
      setError(referenceId, err.message, cezihErrorParts(err).code, cezihErrorParts(err).diagnostics)
    },
  })
}

export function useRetrieveDocument() {
  return useMutation({
    mutationFn: async ({ id, contentUrl, documentOid }: { id: string; contentUrl?: string; documentOid?: string; recordId?: string }) => {
      let endpoint = `/cezih/e-nalaz/${id}/document`
      if (contentUrl) {
        endpoint += `?url=${encodeURIComponent(contentUrl)}`
      } else if (documentOid) {
        endpoint += `?oid=${encodeURIComponent(documentOid)}`
      }
      const response = await api.fetchRaw(endpoint)
      return response.blob()
    },
    onError: (err, vars) => {
      showCezihErrorToast(err)
      const rowId = vars.recordId || vars.id
      if (rowId) {
        setError(rowId, err.message, cezihErrorParts(err).code, cezihErrorParts(err).diagnostics)
      }
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
    onError: (err) => toast.error(err.message),
  })
}

/** Import a patient from CEZIH by any identifier (MBO, EHIC, passport).
 *  Unlike useImportPatientFromCezih, works for foreigners too — stores
 *  passport/EHIC/CEZIH-ID into the dedicated patient columns. */
export function useImportPatientByIdentifier() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      identifier_type,
      identifier_value,
    }: {
      identifier_type: AdhocIdentifierType
      identifier_value: string
    }) =>
      api.post<CezihPatientImport & {
        broj_putovnice: string | null
        ehic_broj: string | null
        cezih_patient_id: string | null
        already_exists: boolean
      }>("/cezih/import-patient-by-identifier", { identifier_type, identifier_value }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["patients"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "activity"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "patients", "search"] })
    },
    onError: (err) => toast.error(err.message),
  })
}
