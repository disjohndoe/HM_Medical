import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/api-client"

export interface Session {
  id: string
  user_id: string
  user_ime: string
  user_prezime: string
  user_email: string
  created_at: string
  expires_at: string
}

export function useSessions() {
  return useQuery({
    queryKey: ["sessions"],
    queryFn: () => api.get<Session[]>("/auth/sessions"),
  })
}

export function useRevokeSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sessionId: string) =>
      api.delete(`/auth/sessions/${sessionId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] })
      queryClient.invalidateQueries({ queryKey: ["plan", "usage"] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}

export function useRevokeOtherSessions() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => {
      // refresh_token is sent via httpOnly cookie — backend reads it from cookie
      return api.post<{ revoked_count: number }>("/auth/sessions/revoke-others", {
        refresh_token: "cookie",
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] })
      queryClient.invalidateQueries({ queryKey: ["plan", "usage"] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}

export function useCleanupTokens() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () =>
      api.post<{ cleaned_count: number }>("/auth/sessions/cleanup", {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] })
      queryClient.invalidateQueries({ queryKey: ["plan", "usage"] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}
