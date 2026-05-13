"use client"

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
import { useRecordTypes, useRecordTypeMaps } from "@/lib/hooks/use-record-types"
import {
  useCreateMedicalRecord,
  useUpdateMedicalRecord,
} from "@/lib/hooks/use-medical-records"
import { useUploadDocument } from "@/lib/hooks/use-documents"
import { useDrugSearch, useSendENalaz, useListVisits, useRetrieveCases, useDtsSearch, useIcd10Search } from "@/lib/hooks/use-cezih"
import { useResolveDtsProcedure, useCreatePerformed, usePerformedProcedures } from "@/lib/hooks/use-procedures"
import { useAppointments } from "@/lib/hooks/use-appointments"
import { formatDateHR, formatDateTimeHR } from "@/lib/utils"
import { useAuth } from "@/lib/auth"
import { CEZIH_DOC_TYPE_BY_TIP, getAllowedDocTypes, APPOINTMENT_VRSTA } from "@/lib/constants"
import type { MedicalRecord, MedicalRecordCreate, MedicalRecordUpdate, PreporucenaTerapijaEntry, LijekItem, CodeSystemItem } from "@/lib/types"

const recordSchema = z.object({
  datum: z.string().min(1, "Datum je obavezan"),
  tip: z.string().min(1, "Tip je obavezan"),
  dijagnoza_mkb: z.string().optional(),
  dijagnoza_tekst: z.string().optional(),
  sadrzaj: z.string().min(10, "Anamneza mora imati najmanje 10 znakova"),
  appointment_id: z.string().optional(),
})

type RecordFormData = z.infer<typeof recordSchema>

interface RecordFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  patientId: string
  record?: MedicalRecord | null
  onSaved?: (record: MedicalRecord) => void | Promise<void>
  submitLabel?: string
  submitOverride?: (payload: MedicalRecordUpdate & { encounter_id?: string; case_id?: string }) => Promise<void>
  mode?: "create" | "edit"
  title?: string
  subtitle?: string
  hasCezihIdentifier?: boolean
}

const ACCEPTED_TYPES = ".jpeg,.jpg,.png,.pdf"
const MAX_SIZE_MB = 10

interface PendingProcedure {
  procedure_id: string
  dts_code: string
  dts_display: string
  napomena: string
}

export function RecordForm({ open, onOpenChange, patientId, record, onSaved, submitLabel, submitOverride, mode, title, subtitle, hasCezihIdentifier }: RecordFormProps) {
  const isEdit = mode === "edit" || (mode === undefined && !!record)
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
    setValue,
    watch,
    formState: { errors },
  } = useForm<RecordFormData>({
    resolver: standardSchemaResolver(recordSchema),
  })

  // CEZIH visit/case selection
  const [selectedEncounterId, setSelectedEncounterId] = useState("")
  const [selectedCaseId, setSelectedCaseId] = useState("")
  const [cezihSending, setCezihSending] = useState(false)
  const sendENalaz = useSendENalaz()
  const { isCezihEligible } = useRecordTypeMaps()
  const watchedTip = watch("tip")
  const isEligibleType = isCezihEligible.has(watchedTip ?? "")

  // ICD-10 (MKB-10) search popover
  const [icd10Open, setIcd10Open] = useState(false)
  const [icd10Query, setIcd10Query] = useState("")
  const { data: icd10Results, isLoading: icd10Loading } = useIcd10Search(icd10Query)

  // Appointments for this patient (selector below). Limit 200 is the API max;
  // sufficient for a single patient's history in any realistic clinic.
  const { data: appointmentsData } = useAppointments(undefined, undefined, undefined, undefined, 0, 200, patientId)
  const patientAppointments = appointmentsData?.items ?? []

  // Inline postupci (DTS procedures)
  const createPerformed = useCreatePerformed()
  const resolveDts = useResolveDtsProcedure()
  const [dtsQuery, setDtsQuery] = useState("")
  const [dtsSearchOpen, setDtsSearchOpen] = useState(false)
  const { data: dtsResults, isLoading: dtsLoading } = useDtsSearch(dtsQuery)
  const [pendingProcedures, setPendingProcedures] = useState<PendingProcedure[]>([])

  // Edit mode: load existing performed procedures for this record
  const { data: existingPerformed } = usePerformedProcedures(
    undefined, undefined, undefined, undefined, record?.id, 0, 100,
  )
  const [removedExistingIds, setRemovedExistingIds] = useState<Set<string>>(new Set())

  const existingItems = (existingPerformed?.items ?? []).filter((p) => !removedExistingIds.has(p.id))

  // Filter the tip picker by what the clinic's šifra djelatnosti can emit.
  const { user, tenant } = useAuth()
  const djelatnostCode = user?.djelatnost_code || tenant?.djelatnost_code || null
  const isExamTenant = !!tenant?.is_exam_tenant
  const allowedDocTypes = new Set<string>(getAllowedDocTypes(djelatnostCode, isExamTenant))

  // Two CEZIH flags, derived from the same eligibility:
  // - cezihAutoSendOnCreate: create-and-send-to-CEZIH happy path (was the
  //   old `shouldSendToCezih`). Requires non-edit + CEZIH identifier + eligible type.
  // - cezihShowLinkSelectors: show the Posjeta/Slučaj picker. True whenever
  //   we'd auto-send on create, OR we're editing a record that's already on
  //   CEZIH (so the doctor can re-link the replaced document).
  const cezihAutoSendOnCreate = !isEdit && !!hasCezihIdentifier && isEligibleType
  const cezihShowLinkSelectors =
    !!hasCezihIdentifier && isEligibleType && (!isEdit || !!record?.cezih_reference_id)
  const { data: visitsData } = useListVisits(cezihShowLinkSelectors ? patientId : "")
  const { data: casesData } = useRetrieveCases(cezihShowLinkSelectors ? patientId : "")

  type VisitItem = { visit_id: string; status: string; period_start?: string; visit_type_display?: string }
  type CaseItem = { case_id: string; clinical_status: string; icd_code?: string; icd_display?: string }
  const visits = ((visitsData as { visits?: VisitItem[] })?.visits ?? []) as VisitItem[]
  const cases = ((casesData as { cases?: CaseItem[] })?.cases ?? []) as CaseItem[]
  const TERMINAL_VISIT_STATUSES = new Set(["finished", "cancelled", "entered-in-error"])
  const TERMINAL_CASE_STATUSES = new Set(["resolved", "inactive", "entered-in-error"])
  const activeVisits = visits.filter((v) => !TERMINAL_VISIT_STATUSES.has(v.status))
  const activeCases = cases.filter((c) => !TERMINAL_CASE_STATUSES.has(c.clinical_status))

  // Auto-select first visit/case on CREATE only - edit mode pre-populates
  // from record.cezih_encounter_id/case_id in the reset block instead.
  useEffect(() => {
    if (cezihAutoSendOnCreate && activeVisits.length > 0 && !selectedEncounterId) {
      setSelectedEncounterId(activeVisits[0].visit_id)
    }
    if (cezihAutoSendOnCreate && activeCases.length > 0 && !selectedCaseId) {
      setSelectedCaseId(activeCases[0].case_id)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cezihAutoSendOnCreate, activeVisits.length, activeCases.length])

  // Auto-populate dijagnoza_mkb when the doctor selects/changes a case.
  // Fires in both create and edit (re-link) modes - doctor can override via
  // the visible MKB-10 input or the search popover.
  useEffect(() => {
    if (!selectedCaseId || !cezihShowLinkSelectors) return
    const selectedCase = activeCases.find((c) => c.case_id === selectedCaseId)
    if (selectedCase?.icd_code) {
      setValue("dijagnoza_mkb", selectedCase.icd_code, { shouldValidate: true })
      if (selectedCase.icd_display) {
        setValue("dijagnoza_tekst", selectedCase.icd_display)
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCaseId, cezihShowLinkSelectors])

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
    if (!open) return
    setAttachedFile(null)
    setDrugSearchQuery("")
    setDrugSearchOpen(false)
    setIcd10Open(false)
    setIcd10Query("")
    // In edit mode, pre-populate encounter/case from the record so the
    // selectors show the current link. Create mode starts empty and auto-
    // selects the first active visit/case in the effect above.
    setSelectedEncounterId(isEdit ? (record?.cezih_encounter_id ?? "") : "")
    setSelectedCaseId(isEdit ? (record?.cezih_case_id ?? "") : "")
    setCezihSending(false)
    setDtsQuery("")
    setDtsSearchOpen(false)
    setPendingProcedures([])
    setRemovedExistingIds(new Set())
    if (record) {
      setTherapy(record.preporucena_terapija ?? [])
      reset({
        datum: record.datum.split("T")[0],
        tip: record.tip,
        dijagnoza_mkb: record.dijagnoza_mkb ?? undefined,
        dijagnoza_tekst: record.dijagnoza_tekst ?? undefined,
        sadrzaj: record.sadrzaj,
        appointment_id: record.appointment_id ?? "",
      })
    } else {
      setTherapy([])
      reset({
        datum: new Date().toISOString().split("T")[0],
        tip: "",
        dijagnoza_mkb: undefined,
        dijagnoza_tekst: undefined,
        sadrzaj: "",
        appointment_id: "",
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, record?.id, reset, isEdit])

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

  // DTS procedure handlers
  async function handleAddDtsProcedure(item: CodeSystemItem) {
    try {
      const proc = await resolveDts.mutateAsync(item.code)
      setPendingProcedures((prev) => [
        ...prev,
        {
          procedure_id: proc.id,
          dts_code: item.code,
          dts_display: item.display,
          napomena: "",
        },
      ])
      setDtsSearchOpen(false)
      setDtsQuery("")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Greška pri dohvaćanju postupka")
    }
  }

  function handleRemovePendingProcedure(index: number) {
    setPendingProcedures((prev) => prev.filter((_, i) => i !== index))
  }

  function handleUpdatePendingProcedure(index: number, field: keyof PendingProcedure, value: string) {
    setPendingProcedures((prev) => prev.map((p, i) => (i === index ? { ...p, [field]: value } : p)))
  }

  async function saveProcedures(recordId: string) {
    for (const proc of pendingProcedures) {
      await createPerformed.mutateAsync({
        patient_id: patientId,
        procedure_id: proc.procedure_id,
        medical_record_id: recordId,
        datum: new Date().toISOString().split("T")[0],
        napomena: proc.napomena || undefined,
      })
    }
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
          appointment_id: data.appointment_id || null,
        }
        if (submitOverride) {
          setOverrideSubmitting(true)
          try {
            // Persist newly added DTS postupci BEFORE triggering CEZIH replace.
            // The backend builds the postupci section from the performed_procedures
            // table; if we skip this the new procedures never reach the bundle.
            if (pendingProcedures.length > 0) {
              await saveProcedures(record.id)
              setPendingProcedures([])
            }
            // The override owns the CEZIH replace request - pass the form's
            // current encounter/case selection so the doctor can re-link the
            // replaced document. Empty string means "keep existing link"
            // (backend falls back to record.cezih_encounter_id/case_id).
            await submitOverride({
              ...payload,
              encounter_id: cezihShowLinkSelectors ? selectedEncounterId : undefined,
              case_id: cezihShowLinkSelectors ? selectedCaseId : undefined,
            })
          } finally {
            setOverrideSubmitting(false)
          }
        } else {
          const updated = await updateMutation.mutateAsync({ id: record.id, data: payload })
          await saveProcedures(record.id)
          toast.success("Zapis ažuriran")
          onSaved?.(updated)
        }
      } else {
        const payload: MedicalRecordCreate = {
          patient_id: patientId,
          datum: data.datum,
          tip: data.tip,
          dijagnoza_mkb: data.dijagnoza_mkb || null,
          dijagnoza_tekst: data.dijagnoza_tekst || null,
          sadrzaj: data.sadrzaj,
          preporucena_terapija: therapy.length > 0 ? therapy : null,
          appointment_id: data.appointment_id || null,
        }
        const created = await createMutation.mutateAsync(payload)

        if (pendingProcedures.length > 0) {
          await saveProcedures(created.id)
        }

        if (attachedFile) {
          try {
            await uploadDoc.mutateAsync({ patientId, file: attachedFile, kategorija: "nalaz" })
          } catch {
            toast.error("Zapis kreiran, ali prilog nije uploadan")
          }
        }

        // Inline CEZIH send: save succeeded, now send if applicable
        if (cezihAutoSendOnCreate && activeVisits.length > 0 && activeCases.length > 0 && created.id) {
          setCezihSending(true)
          try {
            await sendENalaz.mutateAsync({
              patient_id: patientId,
              record_id: created.id,
              encounter_id: selectedEncounterId,
              case_id: selectedCaseId,
            })
            toast.success("Zapis kreiran i poslan na CEZIH")
          } catch (cezihErr) {
            toast.error(
              `Zapis spremljen, ali slanje na CEZIH nije uspjelo: ${cezihErr instanceof Error ? cezihErr.message : "Nepoznata greška"}`,
              { duration: 8000 },
            )
          } finally {
            setCezihSending(false)
          }
        } else if (!onSaved) {
          toast.success("Zapis kreiran")
        }

        if (onSaved) {
          await onSaved(created)
        }
      }
      onOpenChange(false)
      dialogRef.current?.close()
    } catch (err) {
      if (!submitOverride) {
        toast.error(err instanceof Error ? err.message : "Greška pri spremanju")
      }
    }
  }

  const [overrideSubmitting, setOverrideSubmitting] = useState(false)
  const isSubmitting = createMutation.isPending || updateMutation.isPending || uploadDoc.isPending || overrideSubmitting || cezihSending

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

  const hasProcedures = existingItems.length > 0 || pendingProcedures.length > 0

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
              {title ?? (isEdit ? "Uredi zapis" : "Novi medicinski zapis")}
            </h2>
            <p className="text-muted-foreground text-sm">
              {subtitle ?? (isEdit ? "Promijenite podatke o medicinskom zapisu" : "Kreirajte novi medicinski zapis za pacijenta")}
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
                    {(recordTypes ?? [])
                      .filter((t) => t.is_cezih_eligible)
                      .filter((t) => {
                        const docCode = CEZIH_DOC_TYPE_BY_TIP[t.slug]
                        return !docCode || allowedDocTypes.has(docCode)
                      })
                      .map((t) => (
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
            <Label htmlFor="dijagnoza_mkb">MKB-10 šifra</Label>
            <div className="flex gap-2">
              <Input
                id="dijagnoza_mkb"
                placeholder="npr. J45"
                className="flex-1 font-mono uppercase"
                {...register("dijagnoza_mkb")}
              />
              <Popover open={icd10Open} onOpenChange={setIcd10Open}>
                <PopoverTrigger
                  render={<Button type="button" variant="outline" size="sm" className="shrink-0" />}
                >
                  <Search className="mr-1.5 h-3.5 w-3.5" />
                  Pretraži
                </PopoverTrigger>
                <PopoverContent className="w-[--radix-popover-trigger-width] p-1" align="end" container={dialogContainerRef.current ?? undefined}>
                  <div className="relative">
                    <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 opacity-50 pointer-events-none" />
                    <input
                      placeholder="MKB-10 šifra ili naziv..."
                      value={icd10Query}
                      onChange={(e) => setIcd10Query(e.target.value)}
                      className="h-8 w-full rounded-lg border border-input/30 bg-input/30 pl-7 pr-2 text-sm outline-none focus-visible:border-ring"
                    />
                  </div>
                  <div className="mt-1 max-h-64 overflow-y-auto">
                    {icd10Query.length < 2 ? (
                      <p className="py-4 text-center text-xs text-muted-foreground">Unesite barem 2 znaka</p>
                    ) : icd10Loading ? (
                      <p className="py-4 text-center text-xs text-muted-foreground">Pretraživanje...</p>
                    ) : icd10Results?.length ? (
                      icd10Results.map((item: CodeSystemItem) => (
                        <button
                          key={item.code}
                          type="button"
                          onClick={() => {
                            setValue("dijagnoza_mkb", item.code, { shouldValidate: true })
                            setValue("dijagnoza_tekst", item.display)
                            setIcd10Open(false)
                            setIcd10Query("")
                          }}
                          className="flex w-full items-start gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-muted transition-colors cursor-pointer"
                        >
                          <Plus className="h-3 w-3 shrink-0 mt-0.5" />
                          <div className="flex-1 text-left min-w-0">
                            <span className="font-mono text-xs text-muted-foreground">{item.code}</span>
                            <span className="ml-1.5">{item.display}</span>
                          </div>
                        </button>
                      ))
                    ) : (
                      <p className="py-4 text-center text-xs text-muted-foreground">Nema rezultata</p>
                    )}
                  </div>
                </PopoverContent>
              </Popover>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="dijagnoza">Opis dijagnoze</Label>
            <Textarea
              id="dijagnoza"
              placeholder="Opis dijagnoze"
              className="min-h-[100px]"
              {...register("dijagnoza_tekst")}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="appointment_id">Termin</Label>
            <Controller
              name="appointment_id"
              control={control}
              render={({ field }) => (
                <select
                  id="appointment_id"
                  value={field.value ?? ""}
                  onChange={field.onChange}
                  className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm appearance-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
                >
                  <option value="">- Bez termina -</option>
                  {patientAppointments.map((a) => (
                    <option key={a.id} value={a.id}>
                      {formatDateTimeHR(a.datum_vrijeme)} · {APPOINTMENT_VRSTA[a.vrsta] ?? a.vrsta}
                    </option>
                  ))}
                </select>
              )}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="sadrzaj">Anamneza *</Label>
            <Textarea
              id="sadrzaj"
              placeholder="Unesite anamnezu (najmanje 10 znakova)..."
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

          {/* Primijenjeni postupci (DTS) */}
          <div className="space-y-2">
            <Label>Primijenjeni postupci</Label>
            <p className="text-xs text-muted-foreground">
              DTS postupci iz HZZO šifrarnika - bit će uključeni u e-Nalaz.
            </p>
            <Popover open={dtsSearchOpen} onOpenChange={setDtsSearchOpen}>
              <PopoverTrigger
                render={<Button variant="outline" size="sm" className="w-full justify-start text-muted-foreground" />}
              >
                <Search className="mr-2 h-4 w-4" />
                Pretraži DTS postupke...
              </PopoverTrigger>
              <PopoverContent className="w-[--radix-popover-trigger-width] p-1" align="start" container={dialogContainerRef.current ?? undefined}>
                <div className="relative">
                  <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 opacity-50 pointer-events-none" />
                  <input
                    placeholder="DTS šifra ili naziv (npr. EEG, pregled)..."
                    value={dtsQuery}
                    onChange={(e) => setDtsQuery(e.target.value)}
                    className="h-8 w-full rounded-lg border border-input/30 bg-input/30 pl-7 pr-2 text-sm outline-none focus-visible:border-ring"
                  />
                </div>
                <div className="mt-1 max-h-64 overflow-y-auto">
                  {dtsQuery.length < 2 ? (
                    <p className="py-4 text-center text-xs text-muted-foreground">Unesite barem 2 znaka</p>
                  ) : dtsLoading ? (
                    <p className="py-4 text-center text-xs text-muted-foreground">Pretraživanje...</p>
                  ) : dtsResults?.length ? (
                    dtsResults.map((item) => (
                      <button
                        key={item.code}
                        type="button"
                        onClick={() => handleAddDtsProcedure(item)}
                        className="flex w-full items-start gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-muted transition-colors cursor-pointer"
                      >
                        <Plus className="h-3 w-3 shrink-0 mt-0.5" />
                        <div className="flex-1 text-left min-w-0">
                          <span className="font-mono text-xs text-muted-foreground">{item.code}</span>
                          <span className="ml-1.5">{item.display}</span>
                        </div>
                      </button>
                    ))
                  ) : (
                    <p className="py-4 text-center text-xs text-muted-foreground">Nema rezultata</p>
                  )}
                </div>
              </PopoverContent>
            </Popover>

            {hasProcedures && (
              <div className="space-y-2 pt-1">
                {/* Existing procedures (edit mode) */}
                {existingItems.map((p) => (
                  <div key={p.id} className="rounded-lg border p-2 space-y-1">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <span className="font-mono text-xs text-muted-foreground">
                          {p.dts_code ?? p.procedure_sifra}
                        </span>
                        <span className="ml-1.5 text-sm font-medium">{p.procedure_naziv}</span>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setRemovedExistingIds((prev) => new Set(prev).add(p.id))}
                        className="h-6 w-6 p-0 shrink-0"
                      >
                        <Trash2 className="h-3 w-3 text-destructive" />
                      </Button>
                    </div>
                  </div>
                ))}
                {/* Newly added procedures */}
                {pendingProcedures.map((proc, index) => (
                  <div key={`pending-${index}`} className="rounded-lg border border-dashed p-2 space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <span className="font-mono text-xs text-muted-foreground">{proc.dts_code}</span>
                        <span className="ml-1.5 text-sm font-medium">{proc.dts_display}</span>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemovePendingProcedure(index)}
                        className="h-6 w-6 p-0 shrink-0"
                      >
                        <Trash2 className="h-3 w-3 text-destructive" />
                      </Button>
                    </div>
                    <Input
                      placeholder="Napomena"
                      value={proc.napomena}
                      onChange={(e) => handleUpdatePendingProcedure(index, "napomena", e.target.value)}
                      className="h-7 text-xs"
                    />
                  </div>
                ))}
              </div>
            )}
          </div>

          {cezihShowLinkSelectors && (
            <div className="space-y-3 rounded-lg border bg-sky-50/50 dark:bg-sky-950/20 p-3">
              {activeVisits.length === 0 || activeCases.length === 0 ? (
                <p className="text-xs text-amber-600">
                  Nema aktivnih posjeta ili slučajeva. Prvo kreirajte posjetu i slučaj na CEZIH stranici.
                </p>
              ) : (
                <div className="space-y-2">
                  <p className="text-xs text-muted-foreground">
                    {isEdit
                      ? "Posjeta i slučaj za zamjenu na CEZIH. Promjena re-veže zamijenjeni dokument."
                      : "Odaberite posjetu i slučaj za CEZIH slanje."}
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-xs text-muted-foreground">Posjeta</label>
                      <select
                        value={selectedEncounterId}
                        onChange={(e) => setSelectedEncounterId(e.target.value)}
                        className="w-full rounded border bg-background px-2 py-1.5 text-xs"
                        disabled={cezihSending}
                      >
                        <option value="">— Odaberi posjetu —</option>
                        {activeVisits.map((v) => (
                          <option key={v.visit_id} value={v.visit_id}>
                            {v.period_start ? formatDateHR(v.period_start) : v.visit_id.slice(0, 12)}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground">Slučaj</label>
                      <select
                        value={selectedCaseId}
                        onChange={(e) => setSelectedCaseId(e.target.value)}
                        className="w-full rounded border bg-background px-2 py-1.5 text-xs"
                        disabled={cezihSending}
                      >
                        <option value="">— Odaberi slučaj —</option>
                        {activeCases.map((c) => (
                          <option key={c.case_id} value={c.case_id}>
                            {c.icd_code ? `${c.icd_code} ${c.icd_display || ""}`.trim() : c.case_id.slice(0, 12)}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                  {!isEdit && (!selectedEncounterId || !selectedCaseId) && (
                    <p className="text-xs text-amber-600">
                      {!selectedEncounterId && !selectedCaseId
                        ? "Potrebno je odabrati posjetu i slučaj"
                        : !selectedEncounterId
                          ? "Potrebno je odabrati posjetu"
                          : "Potrebno je odabrati slučaj"}
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

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
            <Button type="submit" disabled={isSubmitting || (cezihAutoSendOnCreate && (activeVisits.length === 0 || activeCases.length === 0 || !selectedEncounterId || !selectedCaseId))}>
              {isSubmitting
                ? cezihSending
                  ? "Slanje na CEZIH..."
                  : "Spremanje..."
                : cezihAutoSendOnCreate && (activeVisits.length === 0 || activeCases.length === 0)
                  ? "Nema aktivnih posjeta/slučajeva"
                  : cezihAutoSendOnCreate
                    ? "Kreiraj i pošalji na CEZIH"
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
