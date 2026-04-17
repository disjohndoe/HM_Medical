"use client"

import { useState } from "react"
import { Plus, Loader2, Building2, ExternalLink, Pencil } from "lucide-react"
import { toast } from "sonner"
import { formatDateTimeHR } from "@/lib/utils"
import { useAuth } from "@/lib/auth"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { SortableTableHead } from "@/components/ui/sortable-table-head"
import { useTableSort } from "@/lib/hooks/use-table-sort"
import {
  useListVisits,
  useCreateVisit,
  useUpdateVisit,
  useVisitAction,
  useRetrieveCases,
} from "@/lib/hooks/use-cezih"
import type { VisitItem } from "@/lib/types"

const NO_CASE = "__none__"

const VISIT_STATUS_COLORS: Record<string, string> = {
  "in-progress": "bg-blue-100 text-blue-800",
  "finished": "bg-green-100 text-green-800",
  "planned": "bg-amber-100 text-amber-800",
  "cancelled": "bg-gray-100 text-gray-800",
  "entered-in-error": "bg-red-100 text-red-800",
}

const VISIT_STATUS_LABELS: Record<string, string> = {
  "in-progress": "U tijeku",
  "finished": "Završena",
  "planned": "Planirana",
  "cancelled": "Otkazana",
  "entered-in-error": "Stornirana",
}

const NACIN_PRIJEMA_LABELS: Record<string, string> = {
  "1": "Hitni prijem",
  "2": "Uputnica PZZ",
  "3": "Premještaj iz druge ustanove",
  "4": "Nastavno liječenje",
  "5": "Premještaj unutar ustanove",
  "6": "Ostalo",
  "7": "Poziv na raniji termin",
  "8": "Telemedicina",
  "9": "Interna uputnica",
  "10": "Program+",
}

const TIP_POSJETE_LABELS: Record<string, string> = {
  "1": "Posjeta LOM",
  "2": "Posjeta SKZZ",
  "3": "Hospitalizacija",
}

const VISIT_ACTIONS = [
  { value: "close", label: "Zatvori" },
  { value: "reopen", label: "Ponovno otvori" },
  { value: "storno", label: "Storniraj" },
]

interface VisitManagementProps {
  patientId: string
  onNavigateToCase?: () => void
  createOpen?: boolean
  onCreateOpenChange?: (open: boolean) => void
}

export function VisitManagement({ patientId, onNavigateToCase, createOpen: createOpenProp, onCreateOpenChange }: VisitManagementProps) {
  const { tenant } = useAuth()
  const { data: visitsData, isLoading } = useListVisits(patientId)
  const createVisit = useCreateVisit()
  const updateVisit = useUpdateVisit()
  const visitAction = useVisitAction()

  // Local cache for tip posjete (CEZIH QEDm doesn't return Encounter.type).
  // Backend mirror persists it server-side now; this is just a belt-and-braces
  // cache covering the window between a mutation and the next refetch.
  const [visitMeta, setVisitMeta] = useState<Record<string, { nacin_prijema?: string; tip_posjete?: string }>>({})

  // Create dialog open (controlled via props when provided)
  const [internalCreateOpen, setInternalCreateOpen] = useState(false)
  const showCreate = createOpenProp ?? internalCreateOpen
  const setShowCreate = (open: boolean) => {
    if (onCreateOpenChange) onCreateOpenChange(open)
    else setInternalCreateOpen(open)
  }
  const [nacinPrijema, setNacinPrijema] = useState("6")
  const [tipPosjete, setTipPosjete] = useState("2")
  const [reason, setReason] = useState("")

  // Action/edit state
  const [actionVisitId, setActionVisitId] = useState<string | null>(null)
  const [editVisitId, setEditVisitId] = useState<string | null>(null)
  const [editReason, setEditReason] = useState("")
  const [editNacinPrijema, setEditNacinPrijema] = useState("")
  const [editTipPosjete, setEditTipPosjete] = useState("2")
  const [editCaseId, setEditCaseId] = useState("")
  const [editPractitionerId, setEditPractitionerId] = useState("")
  const [editPeriodStart, setEditPeriodStart] = useState<string | undefined>()

  const visits = visitsData?.visits ?? []
  const myOrgCode = tenant?.sifra_ustanove || ""
  const { data: casesData } = useRetrieveCases(patientId)
  const activeCases = (casesData?.cases ?? []).filter((c) => c.clinical_status === "active")

  const isExternalVisit = (v: VisitItem) =>
    !!myOrgCode && !!v.service_provider_code && v.service_provider_code !== myOrgCode

  const { sorted: sortedVisits, sortKey: vSortKey, sortDir: vSortDir, toggleSort: toggleVSort } = useTableSort(visits, {
    defaultKey: "period_start",
    defaultDir: "desc",
    primaryBucket: (v: VisitItem) => (isExternalVisit(v) ? 1 : 0),
    keyAccessors: {
      izvor: (v: VisitItem) => (isExternalVisit(v) ? 1 : 0),
      status: (v: VisitItem) => VISIT_STATUS_LABELS[v.status] || v.status,
      nacin_prijema: (v: VisitItem) =>
        v.visit_type_display
          || NACIN_PRIJEMA_LABELS[v.visit_type || visitMeta[v.visit_id]?.nacin_prijema || ""]
          || v.visit_type
          || "",
      tip_posjete: (v: VisitItem) =>
        v.tip_posjete_display
          || TIP_POSJETE_LABELS[v.tip_posjete || visitMeta[v.visit_id]?.tip_posjete || ""]
          || "",
      razlog: (v: VisitItem) => v.reason || "",
      period_end: (v: VisitItem) => v.period_end || null,
      updated_at: (v: VisitItem) => v.updated_at || null,
    },
  })

  const handleCreate = () => {
    createVisit.mutate(
      {
        patient_id: patientId,
        nacin_prijema: nacinPrijema,
        tip_posjete: tipPosjete,
        reason: reason || undefined,
      },
      {
        onSuccess: (res) => {
          toast.success(`Posjeta kreirana: ${res.visit_id}`)
          if (res.visit_id) {
            setVisitMeta((prev) => ({
              ...prev,
              [res.visit_id]: {
                nacin_prijema: res.nacin_prijema || nacinPrijema,
                tip_posjete: res.tip_posjete || tipPosjete,
              },
            }))
          }
          setShowCreate(false)
          setReason("")
        },
        onError: (err) => toast.error(err.message),
      },
    )
  }

  const handleAction = (visitId: string, action: string) => {
    const visit = visits.find((v) => v.visit_id === visitId)
    visitAction.mutate(
      { visitId, action, patientId, periodStart: visit?.period_start },
      {
        onSuccess: () => {
          const label = VISIT_ACTIONS.find((a) => a.value === action)?.label || action
          toast.success(`${label}: ${visitId}`)
          setActionVisitId(null)
        },
        onError: (err) => toast.error(err.message),
      },
    )
  }

  const handleEdit = (visitId: string) => {
    updateVisit.mutate(
      {
        visitId,
        reason: editReason || undefined,
        nacin_prijema: editNacinPrijema || undefined,
        tip_posjete: editTipPosjete || undefined,
        diagnosis_case_id: editCaseId || undefined,
        additional_practitioner_id: editPractitionerId || undefined,
        period_start: editPeriodStart,
        patientId,
      },
      {
        onSuccess: (res) => {
          toast.success("Posjeta ažurirana")
          if (visitId) {
            setVisitMeta((prev) => ({
              ...prev,
              [visitId]: {
                nacin_prijema: res.nacin_prijema || editNacinPrijema,
                tip_posjete: res.tip_posjete || editTipPosjete,
              },
            }))
          }
          cancelEdit()
        },
        onError: (err) => toast.error(err.message),
      },
    )
  }

  const startEdit = (v: VisitItem) => {
    setEditVisitId(v.visit_id)
    setEditReason(v.reason || "")
    setEditNacinPrijema(v.visit_type || "6")
    setEditTipPosjete(v.tip_posjete || "2")
    setEditCaseId(v.diagnosis_case_ids?.[0] || "")
    setEditPractitionerId(v.practitioner_ids?.length > 1 ? v.practitioner_ids[1] : "")
    setEditPeriodStart(v.period_start || undefined)
    setActionVisitId(null)
  }

  const cancelEdit = () => {
    setEditVisitId(null)
    setEditReason("")
    setEditNacinPrijema("")
    setEditTipPosjete("2")
    setEditCaseId("")
    setEditPractitionerId("")
    setEditPeriodStart(undefined)
  }

  const getAvailableActions = (v: VisitItem) => {
    if (v.status === "entered-in-error" || v.status === "cancelled") return []
    if (isExternalVisit(v)) return []
    if (v.status === "in-progress") return VISIT_ACTIONS.filter((a) => a.value === "close" || a.value === "storno")
    if (v.status === "finished") return VISIT_ACTIONS.filter((a) => a.value === "reopen" || a.value === "storno")
    return []
  }

  const canEdit = (v: VisitItem) =>
    !isExternalVisit(v) && (v.status === "in-progress" || v.status === "planned")

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <div className="flex items-center gap-2">
          <CardTitle className="text-base">Posjete</CardTitle>
          {visits.length > 0 && (
            <span className="text-xs text-muted-foreground">
              ({visits.filter((v) => !isExternalVisit(v)).length} naše / {visits.filter(isExternalVisit).length} ostale)
            </span>
          )}
        </div>
        <Button size="sm" variant="outline" onClick={() => setShowCreate(true)}>
          <Plus className="mr-1 h-3.5 w-3.5" />
          Nova posjeta
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <Dialog open={showCreate} onOpenChange={setShowCreate}>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle>Nova posjeta</DialogTitle>
            </DialogHeader>
            <div className="space-y-3 pt-2">
              <div className="space-y-1">
                <Label className="text-xs">Način prijema</Label>
                <Select value={nacinPrijema} onValueChange={(v) => v && setNacinPrijema(v)}>
                  <SelectTrigger>
                    <SelectValue>{NACIN_PRIJEMA_LABELS[nacinPrijema] || nacinPrijema}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(NACIN_PRIJEMA_LABELS).map(([val, label]) => (
                      <SelectItem key={val} value={val}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Tip posjete</Label>
                <Select value={tipPosjete} onValueChange={(v) => v && setTipPosjete(v)}>
                  <SelectTrigger>
                    <SelectValue>{TIP_POSJETE_LABELS[tipPosjete] || tipPosjete}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(TIP_POSJETE_LABELS).map(([val, label]) => (
                      <SelectItem key={val} value={val}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Razlog (opcionalno)</Label>
                <Textarea
                  placeholder="Razlog posjete"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  rows={3}
                />
              </div>
            </div>
            <DialogFooter>
              <Button size="sm" variant="outline" onClick={() => setShowCreate(false)}>Odustani</Button>
              <Button size="sm" onClick={handleCreate} disabled={createVisit.isPending}>
                {createVisit.isPending && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
                Kreiraj posjetu
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
            <Loader2 className="h-4 w-4 animate-spin" />
            Učitavanje posjeta...
          </div>
        ) : visits.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">Nema posjeta za ovog pacijenta</p>
        ) : (
          <div className="space-y-3">
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <SortableTableHead columnKey="izvor" label="Izvor" currentKey={vSortKey} currentDir={vSortDir} onSort={toggleVSort} className="w-[100px]" />
                    <SortableTableHead columnKey="status" label="Status" currentKey={vSortKey} currentDir={vSortDir} onSort={toggleVSort} className="w-[100px]" />
                    <SortableTableHead columnKey="nacin_prijema" label="Način prijema" currentKey={vSortKey} currentDir={vSortDir} onSort={toggleVSort} />
                    <SortableTableHead columnKey="tip_posjete" label="Tip posjete" currentKey={vSortKey} currentDir={vSortDir} onSort={toggleVSort} />
                    <SortableTableHead columnKey="razlog" label="Razlog" currentKey={vSortKey} currentDir={vSortDir} onSort={toggleVSort} />
                    <SortableTableHead columnKey="period_start" label="Početak" currentKey={vSortKey} currentDir={vSortDir} onSort={toggleVSort} />
                    <SortableTableHead columnKey="updated_at" label="Izmjena" currentKey={vSortKey} currentDir={vSortDir} onSort={toggleVSort} />
                    <SortableTableHead columnKey="period_end" label="Kraj" currentKey={vSortKey} currentDir={vSortDir} onSort={toggleVSort} />
                    <TableHead className="w-[140px] text-right">Akcije</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sortedVisits.map((v) => {
                    const external = isExternalVisit(v)
                    const actions = getAvailableActions(v)
                    return (
                      <TableRow
                        key={v.visit_id}
                        className={external ? "bg-muted/30" : ""}
                      >
                        <TableCell>
                          {external ? (
                            <Badge variant="outline" className="text-xs gap-1 text-muted-foreground">
                              <ExternalLink className="h-3 w-3" />
                              Vanjska
                            </Badge>
                          ) : (
                            <Badge variant="default" className="bg-primary/90 text-xs gap-1">
                              <Building2 className="h-3 w-3" />
                              Naša
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary" className={VISIT_STATUS_COLORS[v.status] || ""}>
                            {VISIT_STATUS_LABELS[v.status] || v.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm">
                          {v.visit_type_display
                            || NACIN_PRIJEMA_LABELS[v.visit_type || visitMeta[v.visit_id]?.nacin_prijema || ""]
                            || v.visit_type || "—"}
                        </TableCell>
                        <TableCell className="text-sm">
                          {v.tip_posjete_display
                            || TIP_POSJETE_LABELS[v.tip_posjete || visitMeta[v.visit_id]?.tip_posjete || ""]
                            || "—"}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          <div>
                            {v.reason || "—"}
                            {v.diagnosis_case_ids?.length > 0 && (
                              <button
                                type="button"
                                className="ml-1 text-xs text-blue-600 hover:text-blue-800 hover:underline cursor-pointer"
                                title={`Slučajevi: ${v.diagnosis_case_ids.join(", ")} — klikni za prikaz`}
                                onClick={() => onNavigateToCase?.()}
                              >
                                [{v.diagnosis_case_ids.length} slučaj]
                              </button>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="text-sm">
                          {v.period_start ? formatDateTimeHR(v.period_start) : "—"}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {v.updated_at ? formatDateTimeHR(v.updated_at) : "—"}
                        </TableCell>
                        <TableCell className="text-sm">
                          {v.period_end ? formatDateTimeHR(v.period_end) : "—"}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1 flex-wrap">
                            {canEdit(v) && (
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-6 text-xs px-2"
                                onClick={() => startEdit(v)}
                                title="Izmijeni podatke posjete (1.2)"
                              >
                                <Pencil className="h-3 w-3" />
                              </Button>
                            )}
                            {actions.length > 0 && (
                              actionVisitId === v.visit_id ? (
                                <>
                                  {actions.map((a) => (
                                    <Button
                                      key={a.value}
                                      size="sm"
                                      variant={a.value === "storno" ? "destructive" : "outline"}
                                      className="h-6 text-xs px-2"
                                      onClick={() => handleAction(v.visit_id, a.value)}
                                      disabled={visitAction.isPending}
                                    >
                                      {visitAction.isPending && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
                                      {a.label}
                                    </Button>
                                  ))}
                                  <Button size="sm" variant="ghost" className="h-6 text-xs px-2" onClick={() => setActionVisitId(null)}>
                                    ×
                                  </Button>
                                </>
                              ) : (
                                <Button size="sm" variant="ghost" className="h-6 text-xs px-2" onClick={() => setActionVisitId(v.visit_id)}>
                                  Akcije
                                </Button>
                              )
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>

          </div>
        )}
      </CardContent>

      <Dialog open={!!editVisitId} onOpenChange={(open) => { if (!open) cancelEdit() }}>
        <DialogContent className="sm:max-w-[640px]">
          <DialogHeader>
            <DialogTitle>
              Izmjena posjete
              {editVisitId && (
                <span className="ml-2 font-mono text-xs font-normal text-muted-foreground">{editVisitId}</span>
              )}
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Način prijema</Label>
              <Select value={editNacinPrijema} onValueChange={(v) => v && setEditNacinPrijema(v)}>
                <SelectTrigger className="h-8">
                  <SelectValue>{NACIN_PRIJEMA_LABELS[editNacinPrijema] || editNacinPrijema}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(NACIN_PRIJEMA_LABELS).map(([val, label]) => (
                    <SelectItem key={val} value={val}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Tip posjete</Label>
              <Select value={editTipPosjete} onValueChange={(v) => v && setEditTipPosjete(v)}>
                <SelectTrigger className="h-8">
                  <SelectValue>{TIP_POSJETE_LABELS[editTipPosjete] || editTipPosjete}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(TIP_POSJETE_LABELS).map(([val, label]) => (
                    <SelectItem key={val} value={val}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1 col-span-2">
              <Label className="text-xs">Razlog</Label>
              <Textarea
                className="min-h-24 text-sm"
                placeholder="Razlog posjete"
                value={editReason}
                onChange={(e) => setEditReason(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Dodatni liječnik (HZJZ broj)</Label>
              <Input
                className="h-8 text-sm"
                placeholder="HZJZ broj (opcionalno)"
                value={editPractitionerId}
                onChange={(e) => setEditPractitionerId(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Povezani slučaj</Label>
              <Select
                value={editCaseId || NO_CASE}
                onValueChange={(v) => setEditCaseId(!v || v === NO_CASE ? "" : v)}
              >
                <SelectTrigger className="h-8">
                  <SelectValue>
                    {editCaseId
                      ? (() => {
                          const c = activeCases.find((x) => x.case_id === editCaseId)
                          return c ? `${c.icd_code} — ${c.icd_display}` : editCaseId
                        })()
                      : "Bez povezanog slučaja"}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent
                  alignItemWithTrigger={false}
                  className="w-auto min-w-(--anchor-width) max-w-[min(90vw,560px)]"
                >
                  <SelectItem value={NO_CASE}>Bez povezanog slučaja</SelectItem>
                  {activeCases.map((c) => (
                    <SelectItem key={c.case_id} value={c.case_id}>
                      {c.icd_code} — {c.icd_display}
                    </SelectItem>
                  ))}
                  {editCaseId && !activeCases.some((c) => c.case_id === editCaseId) && (
                    <SelectItem value={editCaseId}>{editCaseId} (trenutno odabran)</SelectItem>
                  )}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button size="sm" variant="outline" onClick={cancelEdit}>Odustani</Button>
            <Button
              size="sm"
              onClick={() => editVisitId && handleEdit(editVisitId)}
              disabled={updateVisit.isPending || !editVisitId}
            >
              {updateVisit.isPending && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
              Spremi izmjene
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
