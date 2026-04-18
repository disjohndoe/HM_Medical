import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/api-client"
import type { AgentSecretResponse, PairingTokenResponse, PlanUsage, Tenant } from "@/lib/types"

export function useClinicSettings() {
  return useQuery({
    queryKey: ["settings", "clinic"],
    queryFn: () => api.get<Tenant>("/settings/clinic"),
  })
}

export function useUpdateClinicSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: Partial<Tenant>) =>
      api.patch<Tenant>("/settings/clinic", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings", "clinic"] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}

interface SettingsCezihStatusResponse {
  status: string
  sifra_ustanove: string | null
  oid: string | null
  agent_connected: boolean
  agents_count: number
  last_heartbeat: string | null
}

export function useSettingsCezihStatus(enabled = true) {
  return useQuery({
    queryKey: ["settings", "cezih-status"],
    queryFn: () => api.get<SettingsCezihStatusResponse>("/settings/cezih-status"),
    refetchInterval: enabled ? 15_000 : false,
    staleTime: 10_000,
    enabled,
  })
}

export function useGenerateAgentSecret() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<AgentSecretResponse>("/settings/generate-agent-secret", {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings", "cezih-status"] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}

export function useCreatePairingToken() {
  return useMutation({
    mutationFn: () => api.post<PairingTokenResponse>("/settings/pairing-token", {}),
    onError: (err: Error) => { toast.error(err.message) },
  })
}

export function usePlanUsage() {
  return useQuery({
    queryKey: ["plan", "usage"],
    queryFn: () => api.get<PlanUsage>("/plan/usage"),
  })
}
