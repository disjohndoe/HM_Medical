import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api-client"
import type {
  MedicalRecord,
  MedicalRecordCreate,
  MedicalRecordUpdate,
  PaginatedResponse,
} from "@/lib/types"

export function useMedicalRecords(
  patientId?: string,
  tip?: string,
  dateFrom?: string,
  dateTo?: string,
) {
  const params = new URLSearchParams()
  if (patientId) params.set("patient_id", patientId)
  if (tip) params.set("tip", tip)
  if (dateFrom) params.set("date_from", dateFrom)
  if (dateTo) params.set("date_to", dateTo)
  params.set("limit", "50")

  return useQuery({
    queryKey: ["medical-records", patientId, tip, dateFrom, dateTo],
    queryFn: () =>
      api.get<PaginatedResponse<MedicalRecord>>(
        `/medical-records?${params.toString()}`
      ),
    enabled: !!patientId,
  })
}

export function useCezihUnsentRecords() {
  return useQuery({
    queryKey: ["medical-records", "cezih-unsent"],
    queryFn: () =>
      api.get<PaginatedResponse<MedicalRecord>>(
        "/medical-records?cezih_sent=false&limit=100"
      ),
  })
}

export function useMedicalRecord(id: string) {
  return useQuery({
    queryKey: ["medical-records", id],
    queryFn: () => api.get<MedicalRecord>(`/medical-records/${id}`),
    enabled: !!id,
  })
}

export function useCreateMedicalRecord() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: MedicalRecordCreate) =>
      api.post<MedicalRecord>("/medical-records", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["medical-records"] })
    },
  })
}

export function useUpdateMedicalRecord() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: MedicalRecordUpdate }) =>
      api.patch<MedicalRecord>(`/medical-records/${id}`, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["medical-records"] })
      queryClient.invalidateQueries({
        queryKey: ["medical-records", variables.id],
      })
    },
  })
}
