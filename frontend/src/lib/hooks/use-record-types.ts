import { useMemo } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/api-client"
import { RECORD_TIP, RECORD_TIP_COLORS, CEZIH_MANDATORY_TYPES, CEZIH_ELIGIBLE_TYPES } from "@/lib/constants"
import type { RecordType, RecordTypeCreate, RecordTypeUpdate } from "@/lib/types"

export function useRecordTypes(includeInactive = false) {
  return useQuery({
    queryKey: ["record-types", includeInactive],
    queryFn: () =>
      api.get<RecordType[]>(
        `/record-types${includeInactive ? "?include_inactive=true" : ""}`
      ),
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * Returns lookup maps for record type labels and colors.
 * Falls back to hardcoded constants when API data isn't loaded yet.
 */
export function useRecordTypeMaps() {
  const { data: recordTypes } = useRecordTypes()

  const tipLabelMap = useMemo(() => {
    const map: Record<string, string> = { ...RECORD_TIP }
    for (const rt of recordTypes ?? []) {
      map[rt.slug] = rt.label
    }
    return map
  }, [recordTypes])

  const tipColorMap = useMemo(() => {
    const map: Record<string, string> = { ...RECORD_TIP_COLORS }
    for (const rt of recordTypes ?? []) {
      if (rt.color) map[rt.slug] = rt.color
    }
    return map
  }, [recordTypes])

  const isCezihMandatory = useMemo(() => {
    const set = new Set(CEZIH_MANDATORY_TYPES)
    for (const rt of recordTypes ?? []) {
      if (rt.is_cezih_mandatory) set.add(rt.slug)
    }
    return set
  }, [recordTypes])

  const isCezihEligible = useMemo(() => {
    const set = new Set(CEZIH_ELIGIBLE_TYPES)
    for (const rt of recordTypes ?? []) {
      if (rt.is_cezih_eligible) set.add(rt.slug)
    }
    return set
  }, [recordTypes])

  return {
    recordTypes: recordTypes ?? [],
    tipLabelMap,
    tipColorMap,
    isCezihMandatory,
    isCezihEligible,
  }
}

export function useCreateRecordType() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: RecordTypeCreate) =>
      api.post<RecordType>("/record-types", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["record-types"] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}

export function useUpdateRecordType() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: RecordTypeUpdate }) =>
      api.patch<RecordType>(`/record-types/${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["record-types"] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}

export function useDeleteRecordType() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      api.delete<void>(`/record-types/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["record-types"] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}
