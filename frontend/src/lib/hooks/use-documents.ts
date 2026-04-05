import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api-client"
import type { Document, DocumentUploadResponse } from "@/lib/types"

export function useDocuments(patientId: string) {
  return useQuery({
    queryKey: ["documents", patientId],
    queryFn: () =>
      api.get<Document[]>(`/documents?patient_id=${patientId}`),
    enabled: !!patientId,
  })
}

export function useUploadDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      patientId,
      file,
      kategorija,
    }: {
      patientId: string
      file: File
      kategorija: string
    }) => {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api"

      const formData = new FormData()
      formData.append("file", file)
      formData.append("patient_id", patientId)
      formData.append("kategorija", kategorija)

      const res = await fetch(
        `${API_BASE}/documents/upload`,
        {
          method: "POST",
          credentials: "include",
          body: formData,
        }
      )

      if (!res.ok) {
        const errorBody = await res.json().catch(() => null)
        throw new Error(errorBody?.detail || `Greška pri uploadu: ${res.status}`)
      }

      return res.json() as Promise<DocumentUploadResponse>
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["documents", variables.patientId] })
    },
  })
}

export function useDeleteDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id }: { id: string; patientId: string }) =>
      api.delete(`/documents/${id}`),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["documents", variables.patientId] })
    },
  })
}
