"use client"

import { useMemo, useRef, useState } from "react"
import { Loader2, Shield, FileText, Trash2, CheckCircle2, XCircle, Pencil, Send, Globe, Download } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { CezihWaitOverlay } from "@/components/cezih/cezih-wait-overlay"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { SortableTableHead } from "@/components/ui/sortable-table-head"
import { TablePagination } from "@/components/shared/table-pagination"
import { useTableSort } from "@/lib/hooks/use-table-sort"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { PrescriptionForm } from "@/components/prescriptions/prescription-form"
import { RecordForm } from "@/components/medical-records/record-form"
import { CaseManagement } from "@/components/cezih/case-management"
import { VisitManagement } from "@/components/cezih/visit-management"
import { SendNalazDialog } from "@/components/cezih/send-nalaz-dialog"
import { api } from "@/lib/api-client"
import { usePatientCezihSummary, useInsuranceCheck, useCancelDocument, useReplaceDocumentWithEdit } from "@/lib/hooks/use-cezih"
import { useMedicalRecord } from "@/lib/hooks/use-medical-records"
import { usePermissions } from "@/lib/hooks/use-permissions"
import { OSIGURANJE_STATUS, COUNTRY_HR, RECORD_SENSITIVITY, RECORD_SENSITIVITY_COLORS } from "@/lib/constants"
import { isForeignPatient, type Patient } from "@/lib/types"
import { useRecordTypeMaps } from "@/lib/hooks/use-record-types"
import { formatDateTimeHR } from "@/lib/utils"

const PAGE_SIZE = 30

interface PatientCezihTabProps {
  patientId: string
  patient: Patient
  hasCezihIdentifier: boolean
  subTab?: string
  onSubTabChange?: (v: string) => void
  visitCreateOpen?: boolean
  onVisitCreateOpenChange?: (open: boolean) => void
  caseCreateOpen?: boolean
  onCaseCreateOpenChange?: (open: boolean) => void
}

export function PatientCezihTab({
  patientId,
  patient,
  hasCezihIdentifier,
  subTab,
  onSubTabChange,
  visitCreateOpen,
  onVisitCreateOpenChange,
  caseCreateOpen,
  onCaseCreateOpenChange,
}: PatientCezihTabProps) {
  const isForeign = isForeignPatient(patient)
  const { data: summary, isLoading } = usePatientCezihSummary(patientId)
  const insuranceCheck = useInsuranceCheck()
  const cancelDocument = useCancelDocument()
  const replaceWithEdit = useReplaceDocumentWithEdit()
  const { canUseHzzo } = usePermissions()
  const { tipLabelMap } = useRecordTypeMaps()
  const [internalSubTab, setInternalSubTab] = useState("posjete")
  const cezihSubTab = subTab ?? internalSubTab
  const setCezihSubTab = (v: string) => {
    if (onSubTabChange) onSubTabChange(v)
    else setInternalSubTab(v)
  }
  const [eReceptOpen, setEReceptOpen] = useState(false)
  const [nalazStornoTarget, setNalazStornoTarget] = useState<string | null>(null)
  const [editTarget, setEditTarget] = useState<{ recordId: string; referenceId: string } | null>(null)
  const [localEditRecordId, setLocalEditRecordId] = useState<string | null>(null)
  const [sendTargetRecordId, setSendTargetRecordId] = useState<string | null>(null)
  const { data: localEditRecord } = useMedicalRecord(localEditRecordId ?? "")
  const { data: editRecord } = useMedicalRecord(editTarget?.recordId ?? "")
  const [downloadingId, setDownloadingId] = useState<string | null>(null)
  const downloadingRef = useRef<Set<string>>(new Set())

  const handleDownloadPdf = async (recordId: string, datum: string) => {
    if (downloadingRef.current.has(recordId)) return
    downloadingRef.current.add(recordId)
    setDownloadingId(recordId)
    try {
      const res = await api.fetchRaw(`/medical-records/${recordId}/pdf`)
      const blob = await res.blob()
      const disposition = res.headers.get("content-disposition") || ""
      const match = disposition.match(/filename="?([^"]+)"?/)
      const filename = match ? match[1] : `nalaz_${datum.slice(0, 10)}_${recordId.slice(0, 4)}.pdf`
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
      const digitallySigned = res.headers.get("x-pdf-digitally-signed") === "true"
      if (digitallySigned) {
        toast.success("PDF preuzet i digitalno potpisan.")
      } else {
        toast.warning("PDF preuzet bez digitalnog potpisa.")
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Greška pri preuzimanju PDF-a")
    } finally {
      downloadingRef.current.delete(recordId)
      setDownloadingId(null)
    }
  }

  const enalazRows = (summary?.e_nalaz_history ?? []).map((item) => {
    const replacedMs = item.cezih_last_replaced_at ? new Date(item.cezih_last_replaced_at).getTime() : 0
    const wasReplaced = replacedMs > 0
    return { ...item, _wasReplaced: wasReplaced, _replacedMs: replacedMs }
  })

  const {
    sorted: sortedENalazi,
    sortKey: nSortKey,
    sortDir: nSortDir,
    toggleSort: toggleNSort,
  } = useTableSort(enalazRows, {
    defaultKey: "datum",
    defaultDir: "desc",
    keyAccessors: {
      datum_slanja: (r) => (r.cezih_sent_at ? new Date(r.cezih_sent_at).getTime() : null),
      datum_izmjene: (r) => (r._wasReplaced ? r._replacedMs : null),
      tip: (r) => tipLabelMap[r.tip] || r.tip,
      dijagnoza: (r) => r.dijagnoza_tekst || r.dijagnoza_mkb || "",
      doktor: (r) => `${r.doktor_prezime ?? ""} ${r.doktor_ime ?? ""}`.trim(),
      referenca: (r) => {
        const n = Number(r.reference_id)
        return Number.isFinite(n) ? n : r.reference_id || null
      },
      potpis: (r) => (r.cezih_signed ? 1 : 0),
      status: (r) => (r.cezih_storno ? 1 : 0),
    },
  })

  const [nalaziPage, setNalaziPage] = useState(0)
  const clampedNalaziPage = useMemo(() => {
    const maxPage = Math.max(0, Math.ceil(sortedENalazi.length / PAGE_SIZE) - 1)
    return Math.min(nalaziPage, maxPage)
  }, [sortedENalazi.length, nalaziPage])
  const pagedENalazi = useMemo(
    () => sortedENalazi.slice(clampedNalaziPage * PAGE_SIZE, (clampedNalaziPage + 1) * PAGE_SIZE),
    [sortedENalazi, clampedNalaziPage],
  )

  function handleCheckInsurance() {
    if (isForeign) return
    if (!hasCezihIdentifier) {
      toast.error("Pacijent nema CEZIH identifikator")
      return
    }
    insuranceCheck.mutate(patientId, {
      onSuccess: () => toast.success("Osiguranje provjereno"),
    })
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <Card><CardContent className="p-6"><Skeleton className="h-20 w-full" /></CardContent></Card>
          <Card><CardContent className="p-6"><Skeleton className="h-20 w-full" /></CardContent></Card>
        </div>
        <Card><CardContent className="p-6"><Skeleton className="h-32 w-full" /></CardContent></Card>
      </div>
    )
  }

  const insurance = summary?.insurance
  const statusConfig = insurance?.status_osiguranja
    ? OSIGURANJE_STATUS[insurance.status_osiguranja]
    : null

  return (
    <div className="space-y-4">
      {/* Top row: Insurance + Quick actions */}
      <div className="grid gap-4 md:grid-cols-2">
        {isForeign ? (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <div className="flex items-center gap-2">
                <Globe className="h-4 w-4 text-muted-foreground" />
                <CardTitle className="text-sm font-medium">Strani državljanin</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-1 text-sm">
                {patient.broj_putovnice && (
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground">Putovnica:</span>
                    <span className="font-mono">{patient.broj_putovnice}</span>
                  </div>
                )}
                {patient.ehic_broj && (
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground">EHIC:</span>
                    <span className="font-mono">{patient.ehic_broj}</span>
                  </div>
                )}
                {patient.drzavljanstvo && (
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground">Država:</span>
                    <span>{COUNTRY_HR[patient.drzavljanstvo] || patient.drzavljanstvo}</span>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <div className="flex items-center gap-2">
                <Shield className="h-4 w-4 text-muted-foreground" />
                <CardTitle className="text-sm font-medium">Osiguranje</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              {insurance?.status_osiguranja ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Badge className={statusConfig?.color || ""}>
                      {statusConfig?.label || insurance.status_osiguranja}
                    </Badge>
                    {insurance.osiguravatelj && (
                      <span className="text-sm text-muted-foreground">{insurance.osiguravatelj}</span>
                    )}
                  </div>
                  {insurance.last_checked && (
                    <p className="text-xs text-muted-foreground">
                      Provjereno: {formatDateTimeHR(insurance.last_checked)}
                    </p>
                  )}
                </div>
              ) : (
                <div className="space-y-2">
                  <p className="text-sm text-muted-foreground">Osiguranje nije provjereno</p>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleCheckInsurance}
                    disabled={insuranceCheck.isPending || !hasCezihIdentifier}
                  >
                    {insuranceCheck.isPending && <Loader2 className="mr-2 h-3 w-3 animate-spin" />}
                    Provjeri osiguranje
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Brze akcije</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {canUseHzzo && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setEReceptOpen(true)}
              >
                Novi e-Recept
              </Button>
            )}
            {!isForeign && (
              <Button
                size="sm"
                variant="outline"
                onClick={handleCheckInsurance}
                disabled={insuranceCheck.isPending || !hasCezihIdentifier}
              >
                <Shield className="mr-2 h-3 w-3" />
                Provjeri osiguranje
              </Button>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Sub-tabs: Posjete / Slučajevi / e-Nalazi */}
      <Tabs value={cezihSubTab} onValueChange={setCezihSubTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="posjete">Posjete</TabsTrigger>
          <TabsTrigger value="slucajevi">Slučajevi</TabsTrigger>
          <TabsTrigger value="e-nalazi">e-Nalazi</TabsTrigger>
        </TabsList>

        <TabsContent value="posjete">
          {hasCezihIdentifier ? (
            <VisitManagement
              patientId={patientId}
              onNavigateToCase={() => setCezihSubTab("slucajevi")}
              createOpen={visitCreateOpen}
              onCreateOpenChange={onVisitCreateOpenChange}
            />
          ) : (
            <p className="text-sm text-muted-foreground py-4 text-center">
              Pacijent nema CEZIH identifikator — posjete nisu dostupne
            </p>
          )}
        </TabsContent>

        <TabsContent value="slucajevi">
          {hasCezihIdentifier ? (
            <CaseManagement
              patientId={patientId}
              createOpen={caseCreateOpen}
              onCreateOpenChange={onCaseCreateOpenChange}
            />
          ) : (
            <p className="text-sm text-muted-foreground py-4 text-center">
              Pacijent nema CEZIH identifikator — slučajevi nisu dostupni
            </p>
          )}
        </TabsContent>

        <TabsContent value="e-nalazi">
          <div className="rounded-md border border-blue-200 bg-blue-50 p-3 text-xs text-blue-900 space-y-1">
            <p className="font-medium">Kako koristiti:</p>
            <ul className="list-disc list-inside space-y-0.5">
              <li>
                <strong><Send className="inline h-3 w-3" /> Pošalji</strong> — šalje obavezni nalaz na CEZIH. Zahtijeva digitalni potpis (kartica ili mobilna aplikacija).
              </li>
              <li>
                <strong><Pencil className="inline h-3 w-3" /> Uredi</strong> — otvara uređivanje nalaza i šalje zamjenu na CEZIH.
              </li>
              <li>
                <strong><Trash2 className="inline h-3 w-3" /> Storno</strong> — stornira e-Nalaz na CEZIH. <strong>Radnja se ne može poništiti.</strong>
              </li>
              <li>
                Akcije su onemogućene ako pacijent nema CEZIH identifikator (MBO za hrvatske pacijente, odnosno EHIC/Putovnica za strance).
              </li>
            </ul>
          </div>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-muted-foreground" />
                <CardTitle className="text-sm font-medium">e-Nalaz povijest</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="relative">
              <CezihWaitOverlay isOpen={cancelDocument.isPending || replaceWithEdit.isPending} />
              {!summary?.e_nalaz_history.length ? (
                <p className="text-sm text-muted-foreground text-center py-4">
                  Nema e-Nalaza za ovog pacijenta
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <SortableTableHead columnKey="datum" label="Datum kreiranja" currentKey={nSortKey} currentDir={nSortDir} onSort={toggleNSort} />
                      <SortableTableHead columnKey="datum_slanja" label="Datum slanja" currentKey={nSortKey} currentDir={nSortDir} onSort={toggleNSort} className="hidden sm:table-cell" />
                      <SortableTableHead columnKey="datum_izmjene" label="Datum izmjene" currentKey={nSortKey} currentDir={nSortDir} onSort={toggleNSort} className="hidden sm:table-cell" />
                      <SortableTableHead columnKey="tip" label="Tip" currentKey={nSortKey} currentDir={nSortDir} onSort={toggleNSort} />
                      <SortableTableHead columnKey="dijagnoza" label="Dijagnoza" currentKey={nSortKey} currentDir={nSortDir} onSort={toggleNSort} className="hidden md:table-cell" />
                      <SortableTableHead columnKey="doktor" label="Doktor" currentKey={nSortKey} currentDir={nSortDir} onSort={toggleNSort} className="hidden lg:table-cell" />
                      <SortableTableHead columnKey="referenca" label="Referenca" currentKey={nSortKey} currentDir={nSortDir} onSort={toggleNSort} className="hidden sm:table-cell" />
                      <SortableTableHead columnKey="potpis" label="Potpis" currentKey={nSortKey} currentDir={nSortDir} onSort={toggleNSort} className="hidden md:table-cell" />
                      <SortableTableHead columnKey="status" label="Status" currentKey={nSortKey} currentDir={nSortDir} onSort={toggleNSort} />
                      <TableHead className="text-right">Akcije</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {pagedENalazi.map((item) => (
                      <TableRow key={item.record_id}>
                        <TableCell className="text-sm">{formatDateTimeHR(item.datum)}</TableCell>
                        <TableCell className="hidden sm:table-cell text-sm text-muted-foreground">
                          {item.cezih_sent_at ? formatDateTimeHR(item.cezih_sent_at) : "—"}
                        </TableCell>
                        <TableCell className="hidden sm:table-cell text-sm text-muted-foreground">
                          {item.cezih_last_replaced_at ? formatDateTimeHR(item.cezih_last_replaced_at) : "—"}
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-wrap items-center gap-1">
                            <Badge variant="outline" className="text-xs">
                              {tipLabelMap[item.tip] || item.tip}
                            </Badge>
                            {item.sensitivity && item.sensitivity !== "standard" && (
                              <Badge
                                variant="secondary"
                                className={`text-xs ${RECORD_SENSITIVITY_COLORS[item.sensitivity] || ""}`}
                              >
                                {RECORD_SENSITIVITY[item.sensitivity] || item.sensitivity}
                              </Badge>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="hidden md:table-cell text-sm">
                          {item.dijagnoza_tekst
                            ? `${item.dijagnoza_mkb ? `${item.dijagnoza_mkb} - ` : ""}${item.dijagnoza_tekst}`
                            : item.dijagnoza_mkb || "—"}
                        </TableCell>
                        <TableCell className="hidden lg:table-cell text-sm">
                          {item.doktor_prezime
                            ? `${item.doktor_ime ?? ""} ${item.doktor_prezime}`.trim()
                            : "—"}
                        </TableCell>
                        <TableCell className="hidden sm:table-cell font-mono text-xs">
                          {item.reference_id || "—"}
                        </TableCell>
                        <TableCell className="hidden md:table-cell">
                          {item.cezih_signed ? (
                            <div className="flex items-center gap-1" title={`Potpisano: ${formatDateTimeHR(item.cezih_signed_at || "")}`}>
                              <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
                              <span className="text-xs text-green-700">Da</span>
                            </div>
                          ) : (
                            <div className="flex items-center gap-1" title="Nema digitalnog potpisa">
                              <XCircle className="h-3.5 w-3.5 text-muted-foreground" />
                              <span className="text-xs text-muted-foreground">Ne</span>
                            </div>
                          )}
                        </TableCell>
                        <ENalazStatusCell item={item} />
                        <ENalazActionsCell
                          item={item}
                          downloading={downloadingId === item.record_id}
                          onDownloadPdf={(id) => handleDownloadPdf(id, item.datum)}
                          onLocalEdit={(id) => setLocalEditRecordId(id)}
                          onSend={(id) => setSendTargetRecordId(id)}
                          onReplaceEdit={(recordId, referenceId) => setEditTarget({ recordId, referenceId })}
                          onStorno={(referenceId) => setNalazStornoTarget(referenceId)}
                        />
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
              {sortedENalazi.length > PAGE_SIZE && (
                <div className="mt-3">
                  <TablePagination
                    page={nalaziPage}
                    pageSize={PAGE_SIZE}
                    total={sortedENalazi.length}
                    onPageChange={setNalaziPage}
                  />
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <PrescriptionForm
        open={eReceptOpen}
        onOpenChange={setEReceptOpen}
        patientId={patientId}
      />

      <RecordForm
        open={!!editTarget && !!editRecord}
        onOpenChange={(open) => !open && setEditTarget(null)}
        patientId={patientId}
        record={editRecord ?? null}
        submitLabel="Spremi i zamijeni na CEZIH"
        submitOverride={async (payload) => {
          const referenceId = editTarget?.referenceId
          const recordId = editTarget?.recordId
          if (!referenceId || !recordId) return
          await replaceWithEdit.mutateAsync({
            referenceId,
            record_id: recordId,
            patient_id: patientId,
            encounter_id: editRecord?.cezih_encounter_id ?? "",
            case_id: editRecord?.cezih_case_id ?? "",
            datum: payload.datum ?? null,
            tip: payload.tip ?? null,
            dijagnoza_mkb: payload.dijagnoza_mkb ?? null,
            dijagnoza_tekst: payload.dijagnoza_tekst ?? null,
            sadrzaj: payload.sadrzaj ?? null,
            sensitivity: payload.sensitivity ?? null,
            preporucena_terapija: payload.preporucena_terapija ?? null,
          })
          setEditTarget(null)
          toast.success("e-Nalaz zamijenjen na CEZIH")
        }}
      />

      <SendNalazDialog
        open={!!sendTargetRecordId}
        onOpenChange={(open) => !open && setSendTargetRecordId(null)}
        patientId={patientId}
        hasCezihIdentifier={hasCezihIdentifier}
        onlyRecordId={sendTargetRecordId ?? undefined}
      />

      <RecordForm
        open={!!localEditRecordId && !!localEditRecord}
        onOpenChange={(open) => !open && setLocalEditRecordId(null)}
        patientId={patientId}
        record={localEditRecord ?? null}
        onSaved={() => setLocalEditRecordId(null)}
      />

      {/* Storno e-Nalaz confirmation dialog */}
      <ConfirmDialog
        open={!!nalazStornoTarget}
        onOpenChange={(open: boolean) => !open && setNalazStornoTarget(null)}
        title="Storno e-Nalaza"
        description="Jeste li sigurni da želite stornirati ovaj e-Nalaz na CEZIH? Ova radnja se ne može poništiti."
        confirmLabel="Storniraj"
        variant="destructive"
        onConfirm={() => {
          if (!nalazStornoTarget) return
          // Close dialog immediately — outcome surfaces via toast / row badge.
          // Keeping it open while signing+CEZIH runs (~14s) blocks the table
          // and leaves no graceful exit on error.
          const target = nalazStornoTarget
          setNalazStornoTarget(null)
          cancelDocument.mutate(target, {
            onSuccess: () => toast.success("e-Nalaz storniran"),
          })
        }}
        loading={cancelDocument.isPending}
      />

    </div>
  )
}

function ENalazStatusCell({
  item,
}: {
  item: {
    record_id: string
    reference_id: string | null
    cezih_sent_at: string | null
    cezih_storno: boolean
    cezih_last_replaced_at: string | null
  }
}) {
  const isSent = !!item.cezih_sent_at
  const isReplaced = !!item.cezih_last_replaced_at
  const label = item.cezih_storno
    ? "Storniran"
    : isReplaced
      ? "Zamijenjen"
      : isSent
        ? "Poslan"
        : "Neposlan"
  const cls = item.cezih_storno
    ? "bg-red-100 text-red-800 border-red-200"
    : isReplaced
      ? "bg-blue-100 text-blue-800 border-blue-200"
      : isSent
        ? "bg-green-100 text-green-800 border-green-200"
        : "bg-amber-100 text-amber-800 border-amber-200"

  return (
    <TableCell>
      <Badge variant="outline" className={cls}>{label}</Badge>
    </TableCell>
  )
}

function ENalazActionsCell({
  item,
  downloading,
  onDownloadPdf,
  onLocalEdit,
  onSend,
  onReplaceEdit,
  onStorno,
}: {
  item: {
    record_id: string
    reference_id: string | null
    cezih_sent_at: string | null
    cezih_storno: boolean
  }
  downloading: boolean
  onDownloadPdf: (id: string) => void
  onLocalEdit: (id: string) => void
  onSend: (id: string) => void
  onReplaceEdit: (recordId: string, referenceId: string) => void
  onStorno: (referenceId: string) => void
}) {
  const isUnsent = !item.cezih_sent_at && !item.cezih_storno

  return (
    <TableCell className="text-right">
      <div className="flex justify-end gap-1">
        <Button
          variant="ghost"
          size="sm"
          className="h-8 w-8 p-0"
          onClick={() => onDownloadPdf(item.record_id)}
          disabled={downloading}
          title="Preuzmi PDF"
        >
          {downloading ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Download className="h-3.5 w-3.5" />
          )}
        </Button>
        {isUnsent && (
          <>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => onLocalEdit(item.record_id)}
              title="Uredi nalaz"
            >
              <Pencil className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => onSend(item.record_id)}
              title="Pošalji e-Nalaz na CEZIH"
            >
              <Send className="h-3.5 w-3.5" />
            </Button>
          </>
        )}
        {!item.cezih_storno && item.reference_id && (
          <>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => onReplaceEdit(item.record_id, item.reference_id!)}
              title="Uredi i zamijeni e-Nalaz"
            >
              <Pencil className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0 text-destructive hover:text-destructive"
              onClick={() => onStorno(item.reference_id!)}
              title="Storno e-Nalaza"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </>
        )}
      </div>
    </TableCell>
  )
}
