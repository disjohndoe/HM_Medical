import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/api-client"
import type {
  Document,
  DocumentUploadResponse,
  ImportCezihDocumentResponse,
} from "@/lib/types"

export function useDocuments(
  patientId: string,
  options?: { medicalRecordId?: string | null },
) {
  const medicalRecordId = options?.medicalRecordId ?? null
  return useQuery({
    queryKey: ["documents", patientId, medicalRecordId],
    queryFn: () => {
      const params = new URLSearchParams({ patient_id: patientId })
      if (medicalRecordId) params.set("medical_record_id", medicalRecordId)
      return api.get<Document[]>(`/documents?${params.toString()}`)
    },
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

export function useImportCezihDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: {
      patientId: string
      cezihReferenceId: string
      contentUrl: string
      naziv: string
    }) =>
      api.post<ImportCezihDocumentResponse>("/documents/import-cezih", {
        patient_id: data.patientId,
        cezih_reference_id: data.cezihReferenceId,
        content_url: data.contentUrl,
        naziv: data.naziv,
      }),
    onSuccess: (response, variables) => {
      queryClient.invalidateQueries({ queryKey: ["documents", variables.patientId] })
      const priloziCount = response?.prilozi_imported ?? 0
      if (priloziCount > 0) {
        const priloziLabel = priloziCount === 1 ? "prilog" : "priloga"
        toast.success(
          `Dokument spremljen u Dokumenti + ${priloziCount} ${priloziLabel}`,
        )
      } else {
        toast.success("Dokument spremljen u Dokumenti")
      }
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}

export function useSetRecordAttachments() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      recordId,
      documentIds,
    }: {
      recordId: string
      patientId: string
      documentIds: string[]
    }) =>
      api.patch<Document[]>(`/medical-records/${recordId}/attachments`, {
        document_ids: documentIds,
      }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["documents", variables.patientId] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}
