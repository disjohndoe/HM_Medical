"use client"
/* eslint-disable react-hooks/refs -- react-hook-form handleSubmit is a standard pattern that accesses refs internally */

import { useState, useEffect, useRef, useCallback } from "react"
import { useForm, Controller } from "react-hook-form"
import { z } from "zod"
import { standardSchemaResolver } from "@hookform/resolvers/standard-schema"
import { toast } from "sonner"
import { Upload, X, Plus, Trash2, Search } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { useRecordTypes } from "@/lib/hooks/use-record-types"
import {
  useCreateMedicalRecord,
  useUpdateMedicalRecord,
} from "@/lib/hooks/use-medical-records"
import { useUploadDocument } from "@/lib/hooks/use-documents"
import { useDrugSearch } from "@/lib/hooks/use-cezih"
import type { MedicalRecord, MedicalRecordCreate, MedicalRecordUpdate, PreporucenaTerapijaEntry, LijekItem } from "@/lib/types"

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
  onSaved?: (record: MedicalRecord) => void
  submitLabel?: string
}

const ACCEPTED_TYPES = ".jpeg,.jpg,.png,.pdf"
const MAX_SIZE_MB = 10

export function RecordForm({ open, onOpenChange, patientId, record, onSaved, submitLabel }: RecordFormProps) {
  const isEdit = !!record
  const createMutation = useCreateMedicalRecord()
  const updateMutation = useUpdateMedicalRecord()
  const uploadDoc = useUploadDocument()
  const [attachedFile, setAttachedFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const dialogRef = useRef<HTMLDialogElement>(null)
  const dialogContainerRef = useRef<HTMLDialogElement>(null)
  const [drugSearchOpen, setDrugSearchOpen] = useState(false)
  const [drugSearchQuery, setDrugSearchQuery] = useState("")
  const [therapy, setTherapy] = useState<PreporucenaTerapijaEntry[]>([])
  const { data: drugs } = useDrugSearch(drugSearchQuery)
  const { data: recordTypes } = useRecordTypes()

  const {
    register,
    handleSubmit,
    reset,
    control,
    formState: { errors },
  } = useForm<RecordFormData>({
    resolver: standardSchemaResolver(recordSchema),
  })

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
      setDrugSearchQuery("")
      setDrugSearchOpen(false)
      if (record) {
        setTherapy(record.preporucena_terapija ?? [])
        reset({
          datum: record.datum.split("T")[0],
          tip: record.tip,
          dijagnoza_mkb: record.dijagnoza_mkb ?? undefined,
          dijagnoza_tekst: record.dijagnoza_tekst ?? undefined,
          sadrzaj: record.sadrzaj,
        })
      } else {
        setTherapy([])
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

  const handleAddTherapyDrug = (drug: LijekItem) => {
    if (therapy.some((t) => t.atk === drug.atk && t.naziv === drug.naziv && t.oblik === drug.oblik && t.jacina === drug.jacina)) {
      toast.info("Lijek je već dodan")
      return
    }
    setTherapy((prev) => [
      ...prev,
      { atk: drug.atk, naziv: drug.naziv, jacina: drug.jacina, oblik: drug.oblik, doziranje: "", napomena: "" },
    ])
    setDrugSearchOpen(false)
    setDrugSearchQuery("")
  }

  const handleRemoveTherapyDrug = (index: number) => {
    setTherapy((prev) => prev.filter((_, i) => i !== index))
  }

  const handleUpdateTherapyDrug = (index: number, field: keyof PreporucenaTerapijaEntry, value: string) => {
    setTherapy((prev) => prev.map((d, i) => (i === index ? { ...d, [field]: value } : d)))
  }

  async function onSubmit(data: RecordFormData) {
    try {
      if (isEdit && record) {
        const payload: MedicalRecordUpdate = {
          datum: data.datum,
          tip: data.tip,
          dijagnoza_mkb: data.dijagnoza_mkb || null,
          dijagnoza_tekst: data.dijagnoza_tekst || null,
          sadrzaj: data.sadrzaj,
          preporucena_terapija: therapy.length > 0 ? therapy : null,
        }
        const updated = await updateMutation.mutateAsync({ id: record.id, data: payload })
        toast.success("Zapis ažuriran")
        onSaved?.(updated)
      } else {
        const payload: MedicalRecordCreate = {
          patient_id: patientId,
          datum: data.datum,
          tip: data.tip,
          dijagnoza_mkb: data.dijagnoza_mkb || null,
          dijagnoza_tekst: data.dijagnoza_tekst || null,
          sadrzaj: data.sadrzaj,
          preporucena_terapija: therapy.length > 0 ? therapy : null,
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
      ref={(el) => { (dialogRef as React.MutableRefObject<HTMLDialogElement | null>).current = el; (dialogContainerRef as React.MutableRefObject<HTMLDialogElement | null>).current = el; }}
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
              <Controller
                name="tip"
                control={control}
                render={({ field }) => (
                  <select
                    value={field.value ?? ""}
                    onChange={field.onChange}
                    className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm appearance-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
                  >
                    <option value="" disabled>Odaberite tip</option>
                    {(recordTypes ?? []).filter((t) => t.is_cezih_eligible).map((t) => (
                      <option key={t.slug} value={t.slug}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                )}
              />
              {errors.tip && (
                <p className="text-sm text-destructive">{errors.tip.message}</p>
              )}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="mkb">Dijagnoza MKB</Label>
            <Input id="mkb" placeholder="npr. K04.1" {...register("dijagnoza_mkb")} className="max-w-[200px]" />
          </div>

          <div className="space-y-2">
            <Label htmlFor="dijagnoza">Dijagnoza</Label>
            <Textarea
              id="dijagnoza"
              placeholder="Opis dijagnoze"
              className="min-h-[100px]"
              {...register("dijagnoza_tekst")}
            />
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

          {/* Preporučena terapija */}
          <div className="space-y-2">
            <Label>Preporučena terapija</Label>
            <p className="text-xs text-muted-foreground">
              Lijekovi koje preporuča specijalist — bit će uključeni u e-Nalaz.
            </p>
            <Popover open={drugSearchOpen} onOpenChange={setDrugSearchOpen}>
              <PopoverTrigger
                render={<Button variant="outline" size="sm" className="w-full justify-start text-muted-foreground" />}
              >
                <Search className="mr-2 h-4 w-4" />
                Pretraži lijekove...
              </PopoverTrigger>
              <PopoverContent className="w-[--radix-popover-trigger-width] p-1" align="start" container={dialogContainerRef.current ?? undefined}>
                <div className="relative">
                  <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 opacity-50 pointer-events-none" />
                  <input
                    placeholder="Naziv ili ATK šifra..."
                    value={drugSearchQuery}
                    onChange={(e) => setDrugSearchQuery(e.target.value)}
                    className="h-8 w-full rounded-lg border border-input/30 bg-input/30 pl-7 pr-2 text-sm outline-none focus-visible:border-ring"
                  />
                </div>
                <div className="mt-1 max-h-64 overflow-y-auto">
                  {drugSearchQuery.length < 2 ? (
                    <p className="py-4 text-center text-xs text-muted-foreground">Unesite barem 2 znaka</p>
                  ) : drugs?.length ? (
                    drugs.map((drug, idx) => (
                      <button
                        key={`${drug.atk}-${drug.naziv}-${drug.oblik}-${idx}`}
                        type="button"
                        onClick={() => handleAddTherapyDrug(drug)}
                        className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-muted transition-colors cursor-pointer"
                      >
                        <Plus className="h-3 w-3 shrink-0" />
                        <div className="flex-1 text-left min-w-0">
                          <p className="truncate">{drug.naziv}</p>
                          <p className="text-xs text-muted-foreground truncate">
                            {[drug.oblik, drug.jacina].filter(Boolean).join(" · ")} · ATK: {drug.atk}
                          </p>
                        </div>
                      </button>
                    ))
                  ) : (
                    <p className="py-4 text-center text-xs text-muted-foreground">Nema rezultata</p>
                  )}
                </div>
              </PopoverContent>
            </Popover>

            {therapy.length > 0 && (
              <div className="space-y-2 pt-1">
                {therapy.map((drug, index) => (
                  <div key={index} className="rounded-lg border p-2 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">{drug.naziv}</span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemoveTherapyDrug(index)}
                        className="h-6 w-6 p-0"
                      >
                        <Trash2 className="h-3 w-3 text-destructive" />
                      </Button>
                    </div>
                    {(drug.oblik || drug.jacina) && (
                      <p className="text-xs text-muted-foreground">
                        {drug.oblik}{drug.oblik && drug.jacina ? " · " : ""}{drug.jacina}
                      </p>
                    )}
                    <div className="grid grid-cols-2 gap-2">
                      <Input
                        placeholder="Doziranje (npr. 1-0-1)"
                        value={drug.doziranje}
                        onChange={(e) => handleUpdateTherapyDrug(index, "doziranje", e.target.value)}
                        className="h-7 text-xs"
                      />
                      <Input
                        placeholder="Napomena"
                        value={drug.napomena}
                        onChange={(e) => handleUpdateTherapyDrug(index, "napomena", e.target.value)}
                        className="h-7 text-xs"
                      />
                    </div>
                  </div>
                ))}
              </div>
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
                : submitLabel
                  ? submitLabel
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
