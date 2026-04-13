import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api-client"
import type {
  Biljeska,
  BiljeskaCreate,
  BiljeskaUpdate,
  PaginatedResponse,
} from "@/lib/types"

export function useBiljeske(patientId?: string, kategorija?: string, skip = 0, limit = 20) {
  const params = new URLSearchParams()
  if (patientId) params.set("patient_id", patientId)
  if (kategorija) params.set("kategorija", kategorija)
  params.set("skip", String(skip))
  params.set("limit", String(limit))

  return useQuery({
    queryKey: ["biljeske", patientId, kategorija, skip, limit],
    queryFn: () =>
      api.get<PaginatedResponse<Biljeska>>(
        `/biljeske?${params.toString()}`
      ),
    enabled: !!patientId,
  })
}

export function useCreateBiljeska() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: BiljeskaCreate) =>
      api.post<Biljeska>("/biljeske", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["biljeske"] })
    },
  })
}

export function useUpdateBiljeska() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: BiljeskaUpdate }) =>
      api.patch<Biljeska>(`/biljeske/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["biljeske"] })
    },
  })
}

export function useDeleteBiljeska() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/biljeske/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["biljeske"] })
    },
  })
}
