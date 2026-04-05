import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api-client"
import type { AgentSecretResponse, PlanUsage, Tenant } from "@/lib/types"

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
  })
}

interface CezihStatusResponse {
  status: string
  sifra_ustanove: string | null
  oid: string | null
  agent_connected: boolean
  last_heartbeat: string | null
}

export function useCezihStatus(enabled = true) {
  return useQuery({
    queryKey: ["settings", "cezih-status"],
    queryFn: () => api.get<CezihStatusResponse>("/settings/cezih-status"),
    refetchInterval: enabled ? 15_000 : false,
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
  })
}

export function usePlanUsage() {
  return useQuery({
    queryKey: ["plan", "usage"],
    queryFn: () => api.get<PlanUsage>("/plan/usage"),
  })
}
