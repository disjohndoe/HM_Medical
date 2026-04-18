import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/api-client"
import type { CardStatusResponse, PaginatedResponse, User, UserCreate } from "@/lib/types"

export function useUsers(skip = 0, limit = 50) {
  return useQuery({
    queryKey: ["users", skip, limit],
    queryFn: () =>
      api.get<PaginatedResponse<User>>(`/users?skip=${skip}&limit=${limit}`),
  })
}

export function useCreateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: UserCreate) => api.post<User>("/users", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}

export function useUpdateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<User> }) =>
      api.patch<User>(`/users/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}

export function useDeactivateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/users/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}

export function useBindCard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      userId,
      data,
    }: {
      userId: string
      data: { card_holder_name: string; card_certificate_oib?: string | null }
    }) => api.post<User>(`/users/${userId}/card-binding`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}

export function useUnbindCard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) => api.delete(`/users/${userId}/card-binding`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}

export function useAutoBindCard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) =>
      api.post<User>(`/users/${userId}/card-binding/auto`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}

export function useSelfBindCard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<User>("/users/me/card-binding", {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "status"] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}

export function useSelfUnbindCard() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.delete("/users/me/card-binding"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
      queryClient.invalidateQueries({ queryKey: ["cezih", "status"] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}

export function useCardStatus(enabled = true) {
  return useQuery({
    queryKey: ["card-status"],
    queryFn: () => api.get<CardStatusResponse>("/settings/card-status"),
    refetchInterval: enabled ? 10_000 : false,
    enabled,
  })
}
