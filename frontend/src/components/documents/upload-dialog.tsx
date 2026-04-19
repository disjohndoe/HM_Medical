"use client"

import { useState, useRef, useEffect, useCallback } from "react"
import { Upload, Loader2, X } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { useUploadDocument } from "@/lib/hooks/use-documents"
import { DOCUMENT_KATEGORIJA_OPTIONS } from "@/lib/constants"

interface UploadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  patientId: string
}

const ACCEPTED_TYPES = ".jpeg,.jpg,.png,.pdf"
const MAX_SIZE_MB = 10

export function UploadDialog({ open, onOpenChange, patientId }: UploadDialogProps) {
  const [file, setFile] = useState<File | null>(null)
  const [kategorija, setKategorija] = useState("ostalo")
  const inputRef = useRef<HTMLInputElement>(null)
  const dialogRef = useRef<HTMLDialogElement>(null)
  const upload = useUploadDocument()

  // Sync open prop with native <dialog>
  useEffect(() => {
    const el = dialogRef.current
    if (!el) return
    if (open && !el.open) {
      el.showModal()
    } else if (!open && el.open) {
      el.close()
    }
  }, [open])

  // Handle native close (Esc key, backdrop click)
  const handleNativeClose = useCallback(() => {
    setFile(null)
    setKategorija("ostalo")
    onOpenChange(false)
  }, [onOpenChange])

  useEffect(() => {
    const el = dialogRef.current
    if (!el) return
    el.addEventListener("close", handleNativeClose)
    return () => el.removeEventListener("close", handleNativeClose)
  }, [handleNativeClose])

  // Close on backdrop click
  const handleBackdropClick = useCallback((e: React.MouseEvent<HTMLDialogElement>) => {
    if (e.target === dialogRef.current) {
      handleNativeClose()
      dialogRef.current?.close()
    }
  }, [handleNativeClose])

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0]
    if (!selected) return

    if (selected.size > MAX_SIZE_MB * 1024 * 1024) {
      toast.error(`Datoteka je prevelika (maks ${MAX_SIZE_MB} MB)`)
      return
    }

    const ext = selected.name.split(".").pop()?.toLowerCase()
    if (!["jpeg", "jpg", "png", "pdf"].includes(ext ?? "")) {
      toast.error("Dopuštene vrste: JPEG, PNG, PDF")
      return
    }

    setFile(selected)
  }, [])

  const handleSubmit = () => {
    if (!file) return
    upload.mutate(
      { patientId, file, kategorija },
      {
        onSuccess: () => {
          toast.success("Dokument uploadan")
          setFile(null)
          setKategorija("ostalo")
          onOpenChange(false)
          dialogRef.current?.close()
        },
      }
    )
  }

  const handleClose = () => {
    setFile(null)
    setKategorija("ostalo")
    onOpenChange(false)
    dialogRef.current?.close()
  }

  return (
    <dialog
      ref={dialogRef}
      onClick={handleBackdropClick}
      aria-labelledby="upload-dialog-title"
      className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-[420px] rounded-xl bg-popover p-4 text-sm text-popover-foreground ring-1 ring-foreground/10 shadow-lg backdrop:bg-black/10 backdrop:backdrop-blur-xs m-0"
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 id="upload-dialog-title" className="font-heading text-base font-medium">Upload dokumenta</h2>
          <button
            type="button"
            onClick={handleClose}
            className="rounded-md p-1 hover:bg-muted transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Kategorija</Label>
            <select
              value={kategorija}
              onChange={(e) => setKategorija(e.target.value || "ostalo")}
              className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm appearance-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
            >
              {DOCUMENT_KATEGORIJA_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <Label>Datoteka</Label>
            {file ? (
              <div className="flex items-center gap-2 rounded-lg border p-3">
                <span className="flex-1 text-sm truncate">{file.name}</span>
                <button
                  type="button"
                  onClick={() => { setFile(null); if (inputRef.current) inputRef.current.value = "" }}
                  className="rounded-md p-1 hover:bg-muted transition-colors"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ) : (
              <label
                htmlFor="upload-file-input"
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed p-6 hover:bg-accent/50 transition-colors cursor-pointer"
              >
                <Upload className="h-5 w-5 text-muted-foreground" />
                <span className="text-sm text-muted-foreground">
                  Odaberi datoteku (JPEG, PNG, PDF — max {MAX_SIZE_MB} MB)
                </span>
              </label>
            )}
            <input
              ref={inputRef}
              id="upload-file-input"
              type="file"
              accept={ACCEPTED_TYPES}
              onChange={handleFileChange}
              className="sr-only"
            />
          </div>
        </div>

        <div className="-mx-4 -mb-4 flex justify-end gap-2 rounded-b-xl border-t bg-muted/50 p-4">
          <Button variant="outline" onClick={handleClose}>
            Odustani
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!file || upload.isPending}
          >
            {upload.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            <Upload className="mr-2 h-4 w-4" />
            Upload
          </Button>
        </div>
      </div>
    </dialog>
  )
}
