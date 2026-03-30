"use client"
/* eslint-disable react-hooks/incompatible-library -- react-hook-form watch() is intentionally used */

import { useState, useEffect, useRef, useCallback } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { standardSchemaResolver } from "@hookform/resolvers/standard-schema"
import { toast } from "sonner"
import { Upload, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { RECORD_TIP_OPTIONS } from "@/lib/constants"
import {
  useCreateMedicalRecord,
  useUpdateMedicalRecord,
} from "@/lib/hooks/use-medical-records"
import { useUploadDocument } from "@/lib/hooks/use-documents"
import type { MedicalRecord, MedicalRecordCreate, MedicalRecordUpdate } from "@/lib/types"

const recordSchema = z.object({
  datum: z.string().min(1, "Datum je obavezan"),
  tip: z.string().min(1, "Tip je obavezan"),
  dijagnoza_mkb: z.string().optional(),
  dijagnoza_tekst: z.string().optional(),
  sadrzaj: z.string().min(10, "Sadržaj mora imati najmanje 10 znakova"),
})

type RecordFormData = z.infer<typeof recordSchema>

interface RecordFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  patientId: string
  record?: MedicalRecord | null
}

const ACCEPTED_TYPES = ".jpeg,.jpg,.png,.pdf"
const MAX_SIZE_MB = 10

export function RecordForm({ open, onOpenChange, patientId, record }: RecordFormProps) {
  const isEdit = !!record
  const createMutation = useCreateMedicalRecord()
  const updateMutation = useUpdateMedicalRecord()
  const uploadDoc = useUploadDocument()
  const [attachedFile, setAttachedFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const dialogRef = useRef<HTMLDialogElement>(null)

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { errors },
  } = useForm<RecordFormData>({
    resolver: standardSchemaResolver(recordSchema),
  })

  const tipValue = watch("tip")

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

  // Handle native close (Esc key)
  const handleNativeClose = useCallback(() => {
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
      dialogRef.current?.close()
      onOpenChange(false)
    }
  }, [onOpenChange])

  useEffect(() => {
    if (open) {
      setAttachedFile(null)
      if (record) {
        reset({
          datum: record.datum.split("T")[0],
          tip: record.tip,
          dijagnoza_mkb: record.dijagnoza_mkb ?? undefined,
          dijagnoza_tekst: record.dijagnoza_tekst ?? undefined,
          sadrzaj: record.sadrzaj,
        })
      } else {
        reset({
          datum: new Date().toISOString().split("T")[0],
          tip: "",
          dijagnoza_mkb: undefined,
          dijagnoza_tekst: undefined,
          sadrzaj: "",
        })
      }
    }
  }, [open, record, reset])

  async function onSubmit(data: RecordFormData) {
    try {
      if (isEdit && record) {
        const payload: MedicalRecordUpdate = {
          datum: data.datum,
          tip: data.tip,
          dijagnoza_mkb: data.dijagnoza_mkb || null,
          dijagnoza_tekst: data.dijagnoza_tekst || null,
          sadrzaj: data.sadrzaj,
        }
        await updateMutation.mutateAsync({ id: record.id, data: payload })
        toast.success("Zapis ažuriran")
      } else {
        const payload: MedicalRecordCreate = {
          patient_id: patientId,
          datum: data.datum,
          tip: data.tip,
          dijagnoza_mkb: data.dijagnoza_mkb || null,
          dijagnoza_tekst: data.dijagnoza_tekst || null,
          sadrzaj: data.sadrzaj,
        }
        await createMutation.mutateAsync(payload)
        if (attachedFile) {
          try {
            await uploadDoc.mutateAsync({ patientId, file: attachedFile, kategorija: "nalaz" })
          } catch {
            toast.error("Zapis kreiran, ali prilog nije uploadan")
          }
        }
        toast.success("Zapis kreiran")
      }
      onOpenChange(false)
      dialogRef.current?.close()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Greška pri spremanju")
    }
  }

  const isSubmitting = createMutation.isPending || updateMutation.isPending || uploadDoc.isPending

  const handleFileInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    if (f.size > MAX_SIZE_MB * 1024 * 1024) {
      toast.error(`Datoteka je prevelika (maks ${MAX_SIZE_MB} MB)`)
      return
    }
    setAttachedFile(f)
  }, [])

  const handleClose = () => {
    onOpenChange(false)
    dialogRef.current?.close()
  }

  return (
    <dialog
      ref={dialogRef}
      onClick={handleBackdropClick}
      aria-labelledby="record-form-title"
      className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-[calc(100%-2rem)] sm:max-w-lg max-h-[90vh] overflow-y-auto rounded-xl bg-popover p-4 text-sm text-popover-foreground ring-1 ring-foreground/10 shadow-lg backdrop:bg-black/10 backdrop:backdrop-blur-xs m-0"
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 id="record-form-title" className="font-heading text-base font-medium">
              {isEdit ? "Uredi zapis" : "Novi medicinski zapis"}
            </h2>
            <p className="text-muted-foreground text-sm">
              {isEdit ? "Promijenite podatke o medicinskom zapisu" : "Kreirajte novi medicinski zapis za pacijenta"}
            </p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="rounded-md p-1 hover:bg-muted transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="datum">Datum *</Label>
              <Input id="datum" type="date" {...register("datum")} />
              {errors.datum && (
                <p className="text-sm text-destructive">{errors.datum.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label>Tip *</Label>
              <select
                value={tipValue ?? ""}
                onChange={(e) => setValue("tip", e.target.value)}
                className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm appearance-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
              >
                <option value="" disabled>Odaberite tip</option>
                {RECORD_TIP_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              {errors.tip && (
                <p className="text-sm text-destructive">{errors.tip.message}</p>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="mkb">Dijagnoza MKB</Label>
              <Input id="mkb" placeholder="npr. K04.1" {...register("dijagnoza_mkb")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="dijagnoza">Dijagnoza tekst</Label>
              <Input
                id="dijagnoza"
                placeholder="Opis dijagnoze"
                {...register("dijagnoza_tekst")}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="sadrzaj">Sadržaj *</Label>
            <Textarea
              id="sadrzaj"
              placeholder="Unesite sadržaj medicinskog zapisa (najmanje 10 znakova)..."
              className="min-h-[200px]"
              {...register("sadrzaj")}
            />
            {errors.sadrzaj && (
              <p className="text-sm text-destructive">{errors.sadrzaj.message}</p>
            )}
          </div>

          {!isEdit && (
            <div className="space-y-2">
              <Label>Prilog (opcionalno)</Label>
              {attachedFile ? (
                <div className="flex items-center gap-2 rounded-lg border p-3">
                  <span className="flex-1 text-sm truncate">{attachedFile.name}</span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => { setAttachedFile(null); if (fileInputRef.current) fileInputRef.current.value = "" }}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ) : (
                <label
                  htmlFor="record-file-input"
                  className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed p-4 hover:bg-accent/50 transition-colors cursor-pointer"
                >
                  <Upload className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm text-muted-foreground">
                    Priloži datoteku (JPEG, PNG, PDF — max {MAX_SIZE_MB} MB)
                  </span>
                </label>
              )}
              <input
                ref={fileInputRef}
                id="record-file-input"
                type="file"
                accept={ACCEPTED_TYPES}
                onChange={handleFileInputChange}
                className="sr-only"
              />
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={handleClose}>
              Odustani
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting
                ? "Spremanje..."
                : isEdit
                  ? "Ažuriraj"
                  : "Kreiraj"}
            </Button>
          </div>
        </form>
      </div>
    </dialog>
  )
}
