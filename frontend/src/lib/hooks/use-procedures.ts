import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api-client"
import type {
  PaginatedResponse,
  PerformedProcedure,
  PerformedProcedureCreate,
  Procedure,
  ProcedureCreate,
  ProcedureUpdate,
} from "@/lib/types"

export function useProcedures(
  kategorija?: string,
  search?: string,
  skip = 0,
  limit = 20,
) {
  const params = new URLSearchParams()
  if (kategorija) params.set("kategorija", kategorija)
  if (search) params.set("search", search)
  params.set("skip", String(skip))
  params.set("limit", String(limit))

  return useQuery({
    queryKey: ["procedures", kategorija, search, skip, limit],
    queryFn: () =>
      api.get<PaginatedResponse<Procedure>>(`/procedures?${params.toString()}`),
  })
}

export function useCreateProcedure() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: ProcedureCreate) =>
      api.post<Procedure>("/procedures", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["procedures"] })
    },
  })
}

export function useUpdateProcedure() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ProcedureUpdate }) =>
      api.patch<Procedure>(`/procedures/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["procedures"] })
    },
  })
}

export function useDeleteProcedure() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/procedures/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["procedures"] })
    },
  })
}

export function usePerformedProcedures(
  patientId?: string,
  dateFrom?: string,
  dateTo?: string,
  appointmentId?: string,
  medicalRecordId?: string,
  skip = 0,
  limit = 20,
) {
  const params = new URLSearchParams()
  if (patientId) params.set("patient_id", patientId)
  if (dateFrom) params.set("date_from", dateFrom)
  if (dateTo) params.set("date_to", dateTo)
  if (appointmentId) params.set("appointment_id", appointmentId)
  if (medicalRecordId) params.set("medical_record_id", medicalRecordId)
  params.set("skip", String(skip))
  params.set("limit", String(limit))

  return useQuery({
    queryKey: ["performed-procedures", patientId, dateFrom, dateTo, appointmentId, medicalRecordId, skip, limit],
    queryFn: () =>
      api.get<PaginatedResponse<PerformedProcedure>>(
        `/performed-procedures?${params.toString()}`
      ),
    enabled: !!(patientId || appointmentId || medicalRecordId),
  })
}

export function useCreatePerformed() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: PerformedProcedureCreate) =>
      api.post<PerformedProcedure>("/performed-procedures", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["performed-procedures"] })
    },
  })
}
