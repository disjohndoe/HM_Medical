import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api-client"
import type {
  CaseActionResponse,
  CaseResponse,
  CasesListResponse,
  CezihActivityListResponse,
  CezihDashboardStats,
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
  InsuranceCheckResponse,
  LijekItem,
  OidLookupResponse,
  OrganizationItem,
  PatientCezihSummary,
  CreateVisitRequest,
  PractitionerItem,
  ValueSetExpandResponse,
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
    mutationFn: (mbo: string) =>
      api.post<InsuranceCheckResponse>("/cezih/provjera-osiguranja", { mbo }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cezih", "activity"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "dashboard-stats"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "patient"] })
      queryClient.invalidateQueries({ queryKey: ["patients"] })
    },
  })
}

export function useSendENalaz() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      patient_id,
      record_id,
    }: {
      patient_id: string
      record_id: string
    }) =>
      api.post<ENalazResponse>("/cezih/e-nalaz", { patient_id, record_id }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["medical-records"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "activity"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "dashboard-stats"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "patient"] })
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
      queryClient.invalidateQueries({ queryKey: ["cezih", "patient"] })
    },
  })
}

export function useCancelERecept() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (receptId: string) =>
      api.delete<EReceptStornoResponse>(`/cezih/e-recept/${receptId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cezih", "patient"] })
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
    },
  })
}

// --- Feature 1: Activity Log ---

export function useCezihActivity(limit: number = 20) {
  return useQuery({
    queryKey: ["cezih", "activity", limit],
    queryFn: () =>
      api.get<CezihActivityListResponse>(`/cezih/activity?limit=${limit}`),
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

/** Sidebar badge — updates via mutation invalidation, no polling needed */
export function useCezihNalaziCount() {
  return useQuery({
    queryKey: ["cezih", "dashboard-stats"],
    queryFn: () => api.get<CezihDashboardStats>("/cezih/dashboard-stats"),
    select: (data) => data.neposlani_nalazi ?? 0,
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

export function useOidLookup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (oid: string) =>
      api.post<OidLookupResponse>("/cezih/oid-lookup", { oid }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cezih", "activity"] }),
  })
}


// ============================================================
// TC7: Code System Query
// ============================================================

export function useCodeSystemQuery(system: string, query: string) {
  return useQuery({
    queryKey: ["cezih", "code-system", system, query],
    queryFn: () =>
      api.get<CodeSystemItem[]>(`/cezih/code-system?system=${encodeURIComponent(system)}&q=${encodeURIComponent(query)}`),
    enabled: query.length >= 1,
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
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cezih", "activity"] }),
  })
}


// ============================================================
// TC12-14: Visit Management
// ============================================================

export function useListVisits(mbo: string) {
  return useQuery({
    queryKey: ["cezih", "visits", mbo],
    queryFn: () =>
      api.get<VisitsListResponse>(`/cezih/visits?mbo=${encodeURIComponent(mbo)}`),
    enabled: !!mbo,
  })
}

export function useCreateVisit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateVisitRequest) =>
      api.post<VisitResponse>("/cezih/visits", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cezih", "visits"] })
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
      qc.invalidateQueries({ queryKey: ["cezih", "dashboard-stats"] })
    },
  })
}

export function useUpdateVisit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ visitId, reason, patientMbo }: { visitId: string; reason?: string; patientMbo: string }) =>
      api.patch<VisitResponse>(`/cezih/visits/${visitId}?mbo=${encodeURIComponent(patientMbo)}`, { reason }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cezih", "visits"] })
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
    },
  })
}

export function useVisitAction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ visitId, action, patientMbo }: { visitId: string; action: string; patientMbo: string }) =>
      api.post<VisitResponse>(`/cezih/visits/${visitId}/action?mbo=${encodeURIComponent(patientMbo)}`, { action }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cezih", "visits"] })
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
    },
  })
}


// ============================================================
// TC15-17: Case Management
// ============================================================

export function useRetrieveCases(mbo: string) {
  return useQuery({
    queryKey: ["cezih", "cases", mbo],
    queryFn: () =>
      api.get<CasesListResponse>(`/cezih/cases?mbo=${encodeURIComponent(mbo)}`),
    enabled: !!mbo,
  })
}

export function useCreateCase() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: CreateCaseRequest) =>
      api.post<CaseResponse>("/cezih/cases", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cezih", "cases"] })
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
      qc.invalidateQueries({ queryKey: ["cezih", "dashboard-stats"] })
    },
  })
}

export function useUpdateCaseStatus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ caseId, mbo, action }: { caseId: string; mbo: string; action: string }) =>
      api.put<CaseActionResponse>(`/cezih/cases/${caseId}/status?mbo=${encodeURIComponent(mbo)}`, { action }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cezih", "cases"] })
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
    },
  })
}

export function useUpdateCaseData() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ caseId, mbo, ...data }: {
      caseId: string; mbo: string;
      current_clinical_status?: string; verification_status?: string;
      icd_code?: string; icd_display?: string;
      onset_date?: string; abatement_date?: string; note?: string;
    }) =>
      api.put<CaseActionResponse>(`/cezih/cases/${caseId}/data?mbo=${encodeURIComponent(mbo)}`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cezih", "cases"] })
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
    },
  })
}


// ============================================================
// TC19-22: Document Operations
// ============================================================

export function useDocumentSearch(params: {
  mbo?: string; type?: string; date_from?: string; date_to?: string; status?: string;
}) {
  const searchParams = new URLSearchParams()
  if (params.mbo) searchParams.set("mbo", params.mbo)
  if (params.type) searchParams.set("type", params.type)
  if (params.date_from) searchParams.set("date_from", params.date_from)
  if (params.date_to) searchParams.set("date_to", params.date_to)
  if (params.status) searchParams.set("status", params.status)
  const qs = searchParams.toString()

  return useQuery({
    queryKey: ["cezih", "documents", params],
    queryFn: () =>
      api.get<DocumentSearchItem[]>(`/cezih/documents${qs ? `?${qs}` : ""}`),
    enabled: !!(params.mbo || params.type),
  })
}

export function useReplaceDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (referenceId: string) =>
      api.put<DocumentActionResponse>(`/cezih/e-nalaz/${referenceId}`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cezih", "documents"] })
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
      qc.invalidateQueries({ queryKey: ["cezih", "patient"] })
      qc.invalidateQueries({ queryKey: ["medical-records"] })
    },
  })
}

export function useCancelDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (referenceId: string) =>
      api.delete<DocumentActionResponse>(`/cezih/e-nalaz/${referenceId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cezih", "documents"] })
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
      qc.invalidateQueries({ queryKey: ["cezih", "patient"] })
      qc.invalidateQueries({ queryKey: ["medical-records"] })
    },
  })
}

export function useRetrieveDocument() {
  return useMutation({
    mutationFn: async (referenceId: string) => {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api"
      const response = await fetch(`${API_BASE}/cezih/e-nalaz/${referenceId}/document`, {
        credentials: "include",
      })
      if (!response.ok) throw new Error("Failed to retrieve document")
      return response.blob()
    },
  })
}
