import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/api-client"
import type { PaginatedResponse, Patient, PatientCreate, PatientUpdate } from "@/lib/types"

export function usePatients(search?: string, skip = 0, limit = 20) {
  const params = new URLSearchParams()
  if (search) params.set("search", search)
  params.set("skip", String(skip))
  params.set("limit", String(limit))

  return useQuery({
    queryKey: ["patients", search, skip, limit],
    queryFn: () =>
      api.get<PaginatedResponse<Patient>>(`/patients?${params.toString()}`),
  })
}

export function usePatient(id: string) {
  return useQuery({
    queryKey: ["patients", id],
    queryFn: () => api.get<Patient>(`/patients/${id}`),
    enabled: !!id,
  })
}

export function useCreatePatient() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: PatientCreate) =>
      api.post<Patient>("/patients", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["patients"] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}

export function useUpdatePatient() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: PatientUpdate }) =>
      api.patch<Patient>(`/patients/${id}`, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["patients"] })
      queryClient.invalidateQueries({ queryKey: ["patients", variables.id] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}

export function useDeletePatient() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/patients/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["patients"] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}
