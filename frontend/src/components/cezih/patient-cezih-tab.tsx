"use client"

import { useState } from "react"
import { Loader2, Shield, FileText, Trash2, CheckCircle2, XCircle, Pencil, Send, Globe } from "lucide-react"
import { toast } from "sonner"
import { CezihRowErrorBadge } from "@/lib/hooks/use-cezih-error-state"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
import { useTableSort } from "@/lib/hooks/use-table-sort"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { PrescriptionForm } from "@/components/prescriptions/prescription-form"
import { RecordForm } from "@/components/medical-records/record-form"
import { CaseManagement } from "@/components/cezih/case-management"
import { VisitManagement } from "@/components/cezih/visit-management"
import { SendNalazDialog } from "@/components/cezih/send-nalaz-dialog"
import { usePatientCezihSummary, useInsuranceCheck, useCancelDocument, useReplaceDocumentWithEdit } from "@/lib/hooks/use-cezih"
import { useMedicalRecord } from "@/lib/hooks/use-medical-records"
import { usePermissions } from "@/lib/hooks/use-permissions"
import { OSIGURANJE_STATUS, COUNTRY_HR } from "@/lib/constants"
import { isForeignPatient, type Patient } from "@/lib/types"
import { useRecordTypeMaps } from "@/lib/hooks/use-record-types"
import { formatDateTimeHR } from "@/lib/utils"

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

  const enalazRows = (summary?.e_nalaz_history ?? []).map((item) => {
    const sentMs = item.cezih_sent_at ? new Date(item.cezih_sent_at).getTime() : 0
    const updatedMs = item.updated_at ? new Date(item.updated_at).getTime() : 0
    const wasEdited = sentMs > 0 && updatedMs > sentMs + 60_000
    return { ...item, _wasEdited: wasEdited, _editedMs: wasEdited ? updatedMs : 0 }
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
      datum_izmjene: (r) => (r._wasEdited ? r._editedMs : null),
      tip: (r) => tipLabelMap[r.tip] || r.tip,
      referenca: (r) => {
        const n = Number(r.reference_id)
        return Number.isFinite(n) ? n : r.reference_id || null
      },
      potpis: (r) => (r.cezih_signed ? 1 : 0),
      status: (r) => (r.cezih_storno ? 1 : 0),
    },
  })

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
            <CardContent>
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
                      <SortableTableHead columnKey="referenca" label="Referenca" currentKey={nSortKey} currentDir={nSortDir} onSort={toggleNSort} className="hidden sm:table-cell" />
                      <SortableTableHead columnKey="potpis" label="Potpis" currentKey={nSortKey} currentDir={nSortDir} onSort={toggleNSort} className="hidden md:table-cell" />
                      <SortableTableHead columnKey="status" label="Status" currentKey={nSortKey} currentDir={nSortDir} onSort={toggleNSort} />
                      <TableHead className="text-right">Akcije</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sortedENalazi.map((item) => {
                      const wasEdited = item._wasEdited
                      return (
                      <TableRow key={item.record_id}>
                        <TableCell className="text-sm">{formatDateTimeHR(item.datum)}</TableCell>
                        <TableCell className="hidden sm:table-cell text-sm text-muted-foreground">
                          {item.cezih_sent_at ? formatDateTimeHR(item.cezih_sent_at) : "—"}
                        </TableCell>
                        <TableCell className="hidden sm:table-cell text-sm text-muted-foreground">
                          {wasEdited && item.updated_at ? formatDateTimeHR(item.updated_at) : "—"}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className="text-xs">
                            {tipLabelMap[item.tip] || item.tip}
                          </Badge>
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
                        <TableCell>
                          {(() => {
                            const isSent = !!item.cezih_sent_at
                            const label = item.cezih_storno
                              ? "Storniran"
                              : isSent
                                ? "Poslan"
                                : "Neposlan"
                            const cls = item.cezih_storno
                              ? "bg-red-100 text-red-800 border-red-200"
                              : isSent
                                ? "bg-green-100 text-green-800 border-green-200"
                                : "bg-amber-100 text-amber-800 border-amber-200"
                            return (
                              <Badge variant="outline" className={cls}>
                                {label}
                              </Badge>
                            )
                          })()}
                          <CezihRowErrorBadge rowId={item.reference_id || item.record_id} />
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1">
                            {!item.cezih_sent_at && !item.cezih_storno && (
                              <>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-8 w-8 p-0"
                                  onClick={() => setLocalEditRecordId(item.record_id)}
                                  title="Uredi nalaz"
                                >
                                  <Pencil className="h-3.5 w-3.5" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-8 w-8 p-0"
                                  onClick={() => setSendTargetRecordId(item.record_id)}
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
                                  onClick={() => setEditTarget({ recordId: item.record_id, referenceId: item.reference_id! })}
                                  title="Uredi i zamijeni e-Nalaz"
                                >
                                  <Pencil className="h-3.5 w-3.5" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-8 w-8 p-0 text-destructive hover:text-destructive"
                                  onClick={() => setNalazStornoTarget(item.reference_id)}
                                  title="Storno e-Nalaza"
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </Button>
                              </>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    )
                    })}
                  </TableBody>
                </Table>
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
          cancelDocument.mutate(nalazStornoTarget, {
            onSuccess: () => {
              toast.success("e-Nalaz storniran")
              setNalazStornoTarget(null)
            },
          })
        }}
        loading={cancelDocument.isPending}
      />

    </div>
  )
}
