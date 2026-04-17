import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api-client"
import type {
  Prescription,
  PrescriptionCreate,
  PrescriptionSendResponse,
  PrescriptionUpdate,
  PaginatedResponse,
} from "@/lib/types"

export function usePrescriptions(patientId: string, status?: string, skip = 0, limit = 20) {
  const params = new URLSearchParams()
  params.set("patient_id", patientId)
  if (status) params.set("status", status)
  params.set("skip", String(skip))
  params.set("limit", String(limit))

  return useQuery({
    queryKey: ["prescriptions", patientId, status, skip, limit],
    queryFn: () =>
      api.get<PaginatedResponse<Prescription>>(
        `/prescriptions?${params.toString()}`
      ),
    enabled: !!patientId,
  })
}

export function useCreatePrescription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: PrescriptionCreate) =>
      api.post<Prescription>("/prescriptions", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prescriptions"] })
    },
  })
}

export function useUpdatePrescription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: PrescriptionUpdate }) =>
      api.patch<Prescription>(`/prescriptions/${id}`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prescriptions"] })
      qc.invalidateQueries({ queryKey: ["medical-records"] })
    },
  })
}

export function useDeletePrescription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/prescriptions/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prescriptions"] })
    },
  })
}

export function useSendPrescription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      api.post<PrescriptionSendResponse>(`/prescriptions/${id}/send`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prescriptions"] })
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
      qc.invalidateQueries({ queryKey: ["cezih", "dashboard-stats"] })
      qc.invalidateQueries({ queryKey: ["cezih", "patient"] })
    },
  })
}

export function useStornoPrescription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      api.post<PrescriptionSendResponse>(`/prescriptions/${id}/storno`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prescriptions"] })
      qc.invalidateQueries({ queryKey: ["cezih", "activity"] })
      qc.invalidateQueries({ queryKey: ["cezih", "dashboard-stats"] })
      qc.invalidateQueries({ queryKey: ["cezih", "patient"] })
    },
  })
}
