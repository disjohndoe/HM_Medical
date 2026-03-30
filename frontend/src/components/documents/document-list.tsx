"use client"

import { useState, useCallback, useRef } from "react"
import { Download, Trash2, Loader2, FileText } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { useDocuments, useDeleteDocument } from "@/lib/hooks/use-documents"
import { useDocumentBlob } from "@/lib/hooks/use-document-blob"
import { DocumentPreviewDialog } from "@/components/documents/document-preview-dialog"
import { DOCUMENT_KATEGORIJA, DOCUMENT_KATEGORIJA_COLORS } from "@/lib/constants"
import { formatDateHR, isImage } from "@/lib/utils"
import type { Document } from "@/lib/types"

interface DocumentListProps {
  patientId: string
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function isPreviewable(mimeType: string): boolean {
  return isImage(mimeType) || mimeType === "application/pdf"
}

function DocumentThumbnail({ doc }: { doc: Document }) {
  const isImg = isImage(doc.mime_type)
  const { data: blobUrl } = useDocumentBlob(isImg ? doc.id : null)

  if (isImg && blobUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={blobUrl}
        alt={doc.naziv}
        className="h-10 w-10 rounded object-cover shrink-0"
      />
    )
  }

  return <FileText className="h-5 w-5 text-muted-foreground shrink-0" />
}

export function DocumentList({ patientId }: DocumentListProps) {
  const { data: documents, isLoading } = useDocuments(patientId)
  const deleteDoc = useDeleteDocument()
  const [previewDoc, setPreviewDoc] = useState<Document | null>(null)
  const downloadingRef = useRef<Set<string>>(new Set())

  const handleDownload = useCallback(async (doc: { id: string; naziv: string }) => {
    if (downloadingRef.current.has(doc.id)) return
    downloadingRef.current.add(doc.id)
    try {
      const { api } = await import("@/lib/api-client")
      const res = await api.fetchRaw(`/documents/${doc.id}/download`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = window.document.createElement("a")
      a.href = url
      a.download = doc.naziv
      window.document.body.appendChild(a)
      a.click()
      window.document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {
      toast.error("Greška pri preuzimanju dokumenta")
    } finally {
      downloadingRef.current.delete(doc.id)
    }
  }, [])

  const handleDelete = (doc: { id: string; naziv: string }) => {
    if (!confirm(`Obrisati dokument "${doc.naziv}"?`)) return
    deleteDoc.mutate(
      { id: doc.id, patientId },
      {
        onSuccess: () => toast.success("Dokument obrisan"),
        onError: (err) => toast.error(err.message),
      }
    )
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    )
  }

  if (!documents || documents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8">
        <FileText className="h-8 w-8 text-muted-foreground mb-2" />
        <p className="text-sm text-muted-foreground">Nema uploadanih dokumenata</p>
      </div>
    )
  }

  return (
    <>
      <div className="space-y-2">
        {documents.map((doc) => (
          <div
            key={doc.id}
            className={`flex items-center gap-3 rounded-lg border p-3${
              isPreviewable(doc.mime_type) ? " cursor-pointer hover:bg-accent/50 transition-colors" : ""
            }`}
            onClick={isPreviewable(doc.mime_type) ? () => setPreviewDoc(doc) : undefined}
          >
            <DocumentThumbnail doc={doc} />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{doc.naziv}</p>
              <div className="flex items-center gap-2 mt-0.5">
                <Badge
                  variant="outline"
                  className={DOCUMENT_KATEGORIJA_COLORS[doc.kategorija] ?? ""}
                >
                  {DOCUMENT_KATEGORIJA[doc.kategorija] ?? doc.kategorija}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  {formatFileSize(doc.file_size)}
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatDateHR(doc.created_at)}
                </span>
              </div>
            </div>
            <div className="flex gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleDownload(doc)}
              >
                <Download className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleDelete(doc)}
                disabled={deleteDoc.isPending}
              >
                {deleteDoc.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4 text-destructive" />
                )}
              </Button>
            </div>
          </div>
        ))}
      </div>

      <DocumentPreviewDialog
        document={previewDoc}
        open={!!previewDoc}
        onOpenChange={(open) => { if (!open) setPreviewDoc(null) }}
      />
    </>
  )
}
