"use client"

import { useState, useEffect, useCallback } from "react"
import { Send, Loader2, AlertTriangle, Check, Paperclip, ChevronDown, ChevronRight } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

function CheckIcon({ checked }: { checked: boolean }) {
  return (
    <div className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors ${
      checked ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground/40"
    }`}>
      {checked && <Check className="h-3 w-3" />}
    </div>
  )
}
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { useMedicalRecords } from "@/lib/hooks/use-medical-records"
import { useSendENalaz, useListVisits, useRetrieveCases } from "@/lib/hooks/use-cezih"
import { useRecordTypeMaps } from "@/lib/hooks/use-record-types"
import { formatDateHR } from "@/lib/utils"

interface SendNalazDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  patientId: string
  patientMbo?: string | null
}

export function SendNalazDialog({ open, onOpenChange, patientId, patientMbo }: SendNalazDialogProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [sending, setSending] = useState(false)
  const [progress, setProgress] = useState({ current: 0, total: 0 })
  const [failedRecords, setFailedRecords] = useState<{ id: string; error: string }[]>([])
  const [selectedEncounterId, setSelectedEncounterId] = useState("")
  const [selectedCaseId, setSelectedCaseId] = useState("")
  const [recordEncounter, setRecordEncounter] = useState<Map<string, string>>(new Map())
  const [recordCase, setRecordCase] = useState<Map<string, string>>(new Map())
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())

  const { data } = useMedicalRecords(patientId)
  const sendENalaz = useSendENalaz()
  const { tipLabelMap, tipColorMap, isCezihMandatory } = useRecordTypeMaps()

  // Load patient visits and cases for linking
  const { data: visitsData } = useListVisits(patientMbo || "")
  const { data: casesData } = useRetrieveCases(patientMbo || "")

  type VisitItem = { visit_id: string; status: string; period_start?: string; visit_type_display?: string; service_provider_code?: string | null }
  type CaseItem = { case_id: string; clinical_status: string; icd_code?: string; icd_display?: string }

  const visits = ((visitsData as { visits?: VisitItem[] })?.visits ?? []) as VisitItem[]
  const cases = ((casesData as { cases?: CaseItem[] })?.cases ?? []) as CaseItem[]

  // Exclude terminal states only — anything non-terminal is selectable.
  const TERMINAL_VISIT_STATUSES = new Set(["finished", "cancelled", "entered-in-error"])
  const TERMINAL_CASE_STATUSES = new Set(["resolved", "inactive", "entered-in-error"])
  const activeVisits = visits.filter((v) => !TERMINAL_VISIT_STATUSES.has(v.status))
  const activeCases = cases.filter((c) => !TERMINAL_CASE_STATUSES.has(c.clinical_status))

  const records = data?.items ?? []
  const eligibleRecords = records.filter(
    (r) => isCezihMandatory.has(r.tip) && !r.cezih_sent
  )

  // Seed state when dialog opens or record list arrives
  useEffect(() => {
    if (!open) return
    setSelectedIds(new Set(eligibleRecords.map((r) => r.id)))
    setProgress({ current: 0, total: 0 })
    setFailedRecords([])
    setExpandedIds(new Set())

    // Global defaults = first active visit/case
    const defaultEncounter = activeVisits[0]?.visit_id || ""
    const defaultCase = activeCases[0]?.case_id || ""
    setSelectedEncounterId(defaultEncounter)
    setSelectedCaseId(defaultCase)

    // Per-record maps: seed with stored encounter/case from the record itself
    const nextEnc = new Map<string, string>()
    const nextCase = new Map<string, string>()
    for (const r of eligibleRecords) {
      nextEnc.set(r.id, r.cezih_encounter_id ?? "")
      nextCase.set(r.id, r.cezih_case_id ?? "")
    }
    setRecordEncounter(nextEnc)
    setRecordCase(nextCase)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, eligibleRecords.length, activeVisits.length, activeCases.length])

  const toggleRecord = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleExpanded = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const setRecEnc = (id: string, value: string) => {
    setRecordEncounter((prev) => {
      const next = new Map(prev)
      next.set(id, value)
      return next
    })
  }

  const setRecCase = (id: string, value: string) => {
    setRecordCase((prev) => {
      const next = new Map(prev)
      next.set(id, value)
      return next
    })
  }

  const toggleAll = () => {
    if (selectedIds.size === eligibleRecords.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(eligibleRecords.map((r) => r.id)))
    }
  }

  const resolveEncounter = (id: string): string =>
    recordEncounter.get(id) || selectedEncounterId
  const resolveCase = (id: string): string =>
    recordCase.get(id) || selectedCaseId

  const selectedList = eligibleRecords.filter((r) => selectedIds.has(r.id))
  const missingContextIds = selectedList
    .filter((r) => !resolveEncounter(r.id) || !resolveCase(r.id))
    .map((r) => r.id)
  const canSend =
    selectedList.length > 0 && !!patientMbo && missingContextIds.length === 0

  const handleSend = useCallback(async () => {
    const ids = Array.from(selectedIds)
    if (ids.length === 0) return

    setSending(true)
    setProgress({ current: 0, total: ids.length })
    setFailedRecords([])
    let successCount = 0
    const failed: { id: string; error: string }[] = []

    for (let i = 0; i < ids.length; i++) {
      setProgress({ current: i + 1, total: ids.length })
      const enc = resolveEncounter(ids[i])
      const cs = resolveCase(ids[i])
      try {
        await sendENalaz.mutateAsync({
          patient_id: patientId,
          record_id: ids[i],
          encounter_id: enc,
          case_id: cs,
        })
        successCount++
      } catch (err) {
        failed.push({
          id: ids[i],
          error: err instanceof Error ? err.message : "Nepoznata greška",
        })
      }
    }

    setSending(false)
    setFailedRecords(failed)

    if (successCount > 0) {
      toast.success(`${successCount} nalaz${successCount === 1 ? "" : "a"} poslan${successCount === 1 ? "" : "o"} na CEZIH`)
    }
    if (failed.length > 0) {
      toast.error(
        `${failed.length} nalaz${failed.length === 1 ? "" : "a"} nije uspjelo poslati: ${failed.map((f) => f.error).join("; ")}`,
      )
    }

    if (failed.length === 0) {
      setSelectedIds(new Set())
      onOpenChange(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedIds, patientId, sendENalaz, onOpenChange, recordEncounter, recordCase, selectedEncounterId, selectedCaseId])

  const allSelected = eligibleRecords.length > 0 && selectedIds.size === eligibleRecords.length

  return (
    <Dialog open={open} onOpenChange={sending ? undefined : onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <DialogTitle>Pošalji e-Nalaze (skupno)</DialogTitle>
          </div>
          <DialogDescription>
            Odaberite nalaze koji postaju e-Nalazi na CEZIH-u. Svaki nalaz se šalje s vlastitom posjetom i slučajem.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          {/* Default context (fallback for records without stored encounter/case) */}
          {patientMbo && eligibleRecords.length > 0 && (
            <div className="space-y-2 rounded-lg border bg-muted/30 p-3">
              <p className="text-xs font-medium text-muted-foreground">Zadani kontekst (za nalaze bez spremljenog)</p>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-muted-foreground">Posjeta</label>
                  <select
                    value={selectedEncounterId}
                    onChange={(e) => setSelectedEncounterId(e.target.value)}
                    className="w-full rounded border bg-background px-2 py-1.5 text-xs"
                    disabled={sending}
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
                    disabled={sending}
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
            </div>
          )}

          {eligibleRecords.length === 0 ? (
            <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-8">
              <AlertTriangle className="h-5 w-5 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                Nema neposlanih nalaza za CEZIH
              </p>
            </div>
          ) : (
            <>
              <button
                type="button"
                onClick={toggleAll}
                className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                <CheckIcon checked={allSelected} />
                <span>{allSelected ? "Odznači sve" : "Označi sve"}</span>
              </button>

              <div className="space-y-2 max-h-[420px] overflow-y-auto">
                {eligibleRecords.map((r) => {
                  const recEnc = recordEncounter.get(r.id) ?? ""
                  const recCase = recordCase.get(r.id) ?? ""
                  const encSource: "spremljeno" | "zadano" | "nema" =
                    recEnc ? "spremljeno" : selectedEncounterId ? "zadano" : "nema"
                  const caseSource: "spremljeno" | "zadano" | "nema" =
                    recCase ? "spremljeno" : selectedCaseId ? "zadano" : "nema"
                  const expanded = expandedIds.has(r.id)
                  const isSelected = selectedIds.has(r.id)
                  const hasAttachment = !!r.document_id
                  const isMissing = missingContextIds.includes(r.id)

                  return (
                    <div
                      key={r.id}
                      className={`rounded-lg border transition-colors ${
                        isSelected
                          ? isMissing
                            ? "border-destructive/70 bg-destructive/5"
                            : "border-primary bg-primary/5"
                          : "border-border"
                      }`}
                    >
                      <button
                        type="button"
                        onClick={() => toggleRecord(r.id)}
                        disabled={sending}
                        className="w-full text-left px-3 py-2.5 hover:bg-muted/30 rounded-t-lg"
                      >
                        <div className="flex items-center gap-2">
                          <CheckIcon checked={isSelected} />
                          <Badge
                            variant="secondary"
                            className={`text-xs ${tipColorMap[r.tip] || ""}`}
                          >
                            {tipLabelMap[r.tip] || r.tip}
                          </Badge>
                          {hasAttachment && (
                            <span
                              className="flex items-center gap-1 text-xs text-muted-foreground"
                              title="Prilog će biti poslan uz e-Nalaz"
                            >
                              <Paperclip className="h-3 w-3" />
                              Prilog
                            </span>
                          )}
                          <span className="ml-auto text-xs text-muted-foreground">
                            {formatDateHR(r.datum)}
                          </span>
                        </div>
                        {r.dijagnoza_tekst && (
                          <p className="mt-1 ml-6 text-xs text-muted-foreground truncate">
                            {r.dijagnoza_mkb && <span className="font-mono mr-1">{r.dijagnoza_mkb}</span>}
                            {r.dijagnoza_tekst}
                          </p>
                        )}
                      </button>

                      {/* Per-record visit/case + expand — only for selected records */}
                      {isSelected && (
                        <div className="border-t px-3 py-2 space-y-2" onClick={(e) => e.stopPropagation()}>
                          <div className="grid grid-cols-2 gap-2">
                            <div>
                              <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
                                <span>Posjeta</span>
                                {encSource === "spremljeno" && (
                                  <Badge variant="outline" className="h-4 px-1 text-[9px] border-emerald-500/40 text-emerald-700 dark:text-emerald-400">
                                    Spremljeno
                                  </Badge>
                                )}
                                {encSource === "zadano" && (
                                  <Badge variant="outline" className="h-4 px-1 text-[9px] border-amber-500/40 text-amber-700 dark:text-amber-400">
                                    Zadano
                                  </Badge>
                                )}
                                {encSource === "nema" && (
                                  <Badge variant="outline" className="h-4 px-1 text-[9px] border-destructive/40 text-destructive">
                                    Nedostaje
                                  </Badge>
                                )}
                              </div>
                              <select
                                value={recEnc}
                                onChange={(e) => {
                                  e.stopPropagation()
                                  setRecEnc(r.id, e.target.value)
                                }}
                                onClick={(e) => e.stopPropagation()}
                                className="w-full rounded border bg-background px-2 py-1 text-xs"
                                disabled={sending}
                              >
                                <option value="">— Koristi zadano —</option>
                                {activeVisits.map((v) => (
                                  <option key={v.visit_id} value={v.visit_id}>
                                    {v.period_start ? formatDateHR(v.period_start) : v.visit_id.slice(0, 12)}
                                  </option>
                                ))}
                              </select>
                            </div>
                            <div>
                              <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
                                <span>Slučaj</span>
                                {caseSource === "spremljeno" && (
                                  <Badge variant="outline" className="h-4 px-1 text-[9px] border-emerald-500/40 text-emerald-700 dark:text-emerald-400">
                                    Spremljeno
                                  </Badge>
                                )}
                                {caseSource === "zadano" && (
                                  <Badge variant="outline" className="h-4 px-1 text-[9px] border-amber-500/40 text-amber-700 dark:text-amber-400">
                                    Zadano
                                  </Badge>
                                )}
                                {caseSource === "nema" && (
                                  <Badge variant="outline" className="h-4 px-1 text-[9px] border-destructive/40 text-destructive">
                                    Nedostaje
                                  </Badge>
                                )}
                              </div>
                              <select
                                value={recCase}
                                onChange={(e) => {
                                  e.stopPropagation()
                                  setRecCase(r.id, e.target.value)
                                }}
                                onClick={(e) => e.stopPropagation()}
                                className="w-full rounded border bg-background px-2 py-1 text-xs"
                                disabled={sending}
                              >
                                <option value="">— Koristi zadano —</option>
                                {activeCases.map((c) => (
                                  <option key={c.case_id} value={c.case_id}>
                                    {c.icd_code ? `${c.icd_code} ${c.icd_display || ""}`.trim() : c.case_id.slice(0, 12)}
                                  </option>
                                ))}
                              </select>
                            </div>
                          </div>

                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              toggleExpanded(r.id)
                            }}
                            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                          >
                            {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                            {expanded ? "Sakrij sadržaj" : "Prikaži sadržaj"}
                          </button>

                          {expanded && (
                            <div className="rounded-md bg-muted/40 p-2 space-y-2">
                              {r.sadrzaj && (
                                <pre className="whitespace-pre-wrap text-xs leading-relaxed font-sans">
                                  {r.sadrzaj.length > 500 ? r.sadrzaj.slice(0, 500) + "…" : r.sadrzaj}
                                </pre>
                              )}
                              {r.preporucena_terapija && r.preporucena_terapija.length > 0 && (
                                <div className="pt-1 border-t border-border/40">
                                  <p className="text-[10px] font-medium text-muted-foreground mb-1">Preporučena terapija</p>
                                  <ul className="text-xs space-y-0.5">
                                    {r.preporucena_terapija.map((t, i) => (
                                      <li key={i} className="text-muted-foreground">
                                        <span className="text-foreground">{t.naziv}</span>
                                        {t.jacina && <span> {t.jacina}</span>}
                                        {t.doziranje && <span> · {t.doziranje}</span>}
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              {!r.sadrzaj && !(r.preporucena_terapija && r.preporucena_terapija.length > 0) && (
                                <p className="text-xs text-muted-foreground italic">Nema dodatnog sadržaja.</p>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </>
          )}

          {sending && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Slanje {progress.current}/{progress.total}...</span>
            </div>
          )}

          {failedRecords.length > 0 && !sending && (
            <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 space-y-1">
              <p className="text-sm font-medium text-destructive">
                {failedRecords.length} nalaz{failedRecords.length === 1 ? "" : "a"} nije uspjelo poslati:
              </p>
              {failedRecords.map((f) => {
                const record = eligibleRecords.find((r) => r.id === f.id)
                return (
                  <p key={f.id} className="text-xs text-destructive/80">
                    {record ? `${tipLabelMap[record.tip] || record.tip} (${formatDateHR(record.datum)})` : f.id}: {f.error}
                  </p>
                )
              })}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            onClick={handleSend}
            disabled={!canSend || sending}
            title={
              !patientMbo
                ? "Pacijent nema MBO — potreban za CEZIH"
                : missingContextIds.length > 0
                  ? `${missingContextIds.length} odabran${missingContextIds.length === 1 ? "" : "ih"} nalaz${missingContextIds.length === 1 ? "" : "a"} nema posjetu i/ili slučaj`
                  : undefined
            }
          >
            {sending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Send className="mr-2 h-4 w-4" />
            )}
            {!patientMbo
              ? "MBO nije dostupan"
              : sending
                ? `Slanje ${progress.current}/${progress.total}...`
                : `Pošalji${selectedIds.size > 0 ? ` (${selectedIds.size})` : ""}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
