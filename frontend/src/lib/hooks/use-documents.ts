import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

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
      const formData = new FormData()
      formData.append("file", file)
      formData.append("patient_id", patientId)
      formData.append("kategorija", kategorija)

      return api.postFormData<DocumentUploadResponse>("/documents/upload", formData)
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["documents", variables.patientId] })
    },
    onError: (err: Error) => { toast.error(err.message) },
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
    onError: (err: Error) => { toast.error(err.message) },
  })
}
