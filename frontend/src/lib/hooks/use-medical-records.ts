import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

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
  skip = 0,
  limit = 20,
) {
  const params = new URLSearchParams()
  if (patientId) params.set("patient_id", patientId)
  if (tip) params.set("tip", tip)
  if (dateFrom) params.set("date_from", dateFrom)
  if (dateTo) params.set("date_to", dateTo)
  params.set("skip", String(skip))
  params.set("limit", String(limit))

  return useQuery({
    queryKey: ["medical-records", patientId, tip, dateFrom, dateTo, skip, limit],
    queryFn: () =>
      api.get<PaginatedResponse<MedicalRecord>>(
        `/medical-records?${params.toString()}`
      ),
    enabled: !!patientId,
  })
}

export function useCezihUnsentRecords(skip = 0, limit = 20) {
  return useQuery({
    queryKey: ["medical-records", "cezih-unsent", skip, limit],
    queryFn: () =>
      api.get<PaginatedResponse<MedicalRecord>>(
        `/medical-records?cezih_sent=false&skip=${skip}&limit=${limit}`
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
      queryClient.invalidateQueries({ queryKey: ["prescriptions"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "patient"], exact: false })
      queryClient.invalidateQueries({ queryKey: ["cezih", "documents"], exact: false })
    },
    onError: (err: Error) => { toast.error(err.message) },
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
      queryClient.invalidateQueries({ queryKey: ["prescriptions"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "patient"], exact: false })
      queryClient.invalidateQueries({ queryKey: ["cezih", "documents"], exact: false })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}
