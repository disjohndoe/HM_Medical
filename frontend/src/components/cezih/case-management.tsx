"use client"

import { useState } from "react"
import { FileText, Plus, Loader2, Pencil } from "lucide-react"
import { toast } from "sonner"
import { formatDateTimeHR } from "@/lib/utils"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
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
import { SortableTableHead } from "@/components/ui/sortable-table-head"
import { useTableSort } from "@/lib/hooks/use-table-sort"
import {
  useRetrieveCases,
  useCreateCase,
  useUpdateCaseStatus,
  useUpdateCaseData,
  useIcd10Search,
} from "@/lib/hooks/use-cezih"
import type { CaseItem } from "@/lib/types"

const CLINICAL_STATUS_COLORS: Record<string, string> = {
  active: "bg-blue-100 text-blue-800",
  recurrence: "bg-purple-100 text-purple-800",
  remission: "bg-green-100 text-green-800",
  relapse: "bg-orange-100 text-orange-800",
  inactive: "bg-gray-100 text-gray-800",
  resolved: "bg-gray-100 text-gray-800",
}

const CLINICAL_STATUS_LABELS: Record<string, string> = {
  active: "Aktivan",
  recurrence: "Ponavljajući",
  remission: "Remisija",
  relapse: "Relaps",
  inactive: "Neaktivan",
  resolved: "Zatvoren",
}

const VERIFICATION_STATUS_LABELS: Record<string, string> = {
  unconfirmed: "Nepotvrđen",
  provisional: "Privremena",
  "differential": "Diferencijalna",
  confirmed: "Potvrđen",
  refuted: "Opovrgnut",
  "entered-in-error": "Pogreška unosa",
}

// CEZIH's health-issue-management-verification-status-create ValueSet only accepts
// unconfirmed / provisional / differential / confirmed. refuted and entered-in-error
// are rejected at the server. Filter these out of input pickers but keep labels
// available so we can still render any legacy values that come back from CEZIH.
const CEZIH_VERIFICATION_STATUSES = ["unconfirmed", "provisional", "differential", "confirmed"] as const

// CEZIH case actions — event codes per Simplifier cezih.hr.condition-management/0.2.1:
//   2.1=Create, 2.2=Create recurrence, 2.3=Remission, 2.4=Resolve,
//   2.5=Relapse, 2.6=Data update, 2.7=Delete (NOT shipped — product rule),
//   2.9=Reopen after resolve.
// Delete (2.7) is intentionally omitted from UI per product rule.
// For mistaken entries: use 2.6 Data update + verificationStatus=entered-in-error.
const CASE_ACTIONS = [
  { value: "create_recurring", label: "Ponavljajući slučaj" },
  { value: "remission", label: "Remisija" },
  { value: "relapse", label: "Relaps" },
  { value: "resolve", label: "Zatvori" },
  { value: "reopen", label: "Ponovno otvori" },
]

interface CaseManagementProps {
  patientId: string
  createOpen?: boolean
  onCreateOpenChange?: (open: boolean) => void
}

export function CaseManagement({ patientId, createOpen: createOpenProp, onCreateOpenChange }: CaseManagementProps) {
  const [internalCreateOpen, setInternalCreateOpen] = useState(false)
  const createOpen = createOpenProp ?? internalCreateOpen
  const setCreateOpen = (open: boolean) => {
    if (onCreateOpenChange) onCreateOpenChange(open)
    else setInternalCreateOpen(open)
  }
  const [icdQuery, setIcdQuery] = useState("")
  const [selectedIcd, setSelectedIcd] = useState<{ code: string; display: string } | null>(null)
  const [onsetDate, setOnsetDate] = useState(new Date().toISOString().split("T")[0])
  const [verification, setVerification] = useState("confirmed")
  const [note, setNote] = useState("")
  const [manualCode, setManualCode] = useState("")
  const [manualDisplay, setManualDisplay] = useState("")

  // Edit state
  const [editCaseId, setEditCaseId] = useState<string | null>(null)
  const [editNote, setEditNote] = useState("")
  const [editVerification, setEditVerification] = useState("")
  const [editIcdQuery, setEditIcdQuery] = useState("")
  const [editSelectedIcd, setEditSelectedIcd] = useState<{ code: string; display: string } | null>(null)
  const [editOnsetDate, setEditOnsetDate] = useState("")
  const [editAbatementDate, setEditAbatementDate] = useState("")


  const casesQuery = useRetrieveCases(patientId)
  const createCase = useCreateCase()
  const updateStatus = useUpdateCaseStatus()
  const updateData = useUpdateCaseData()
  const icdSearch = useIcd10Search(icdQuery)
  const editIcdSearch = useIcd10Search(editIcdQuery)

  const handleCreate = () => {
    if (!selectedIcd) {
      toast.error("Odaberite MKB/ICD-10 šifru")
      return
    }
    createCase.mutate(
      {
        patient_id: patientId,
        icd_code: selectedIcd.code,
        icd_display: selectedIcd.display,
        onset_date: onsetDate,
        verification_status: verification,
        note: note || undefined,
      },
      {
        onSuccess: (data) => {
          toast.success(`Slučaj kreiran: ${data.cezih_case_id || data.local_case_id}`)
          setCreateOpen(false)
          setSelectedIcd(null)
          setIcdQuery("")
          setVerification("confirmed")
          setNote("")
        },
        onError: (err) => toast.error(err.message),
      }
    )
  }

  const handleAction = (caseId: string, action: string) => {
    const actionLabel = CASE_ACTIONS.find((a) => a.value === action)?.label || action
    updateStatus.mutate(
      { caseId, patientId, action },
      {
        onSuccess: () => toast.success(`${actionLabel} — uspješno`),
        onError: (err) => toast.error(err.message),
      }
    )
  }

  const startEdit = (c: CaseItem) => {
    setEditCaseId(c.case_id)
    setEditNote(c.note || "")
    setEditVerification(c.verification_status || "unconfirmed")
    setEditSelectedIcd({ code: c.icd_code, display: c.icd_display })
    setEditIcdQuery(`${c.icd_code} — ${c.icd_display}`)
    setEditOnsetDate(c.onset_date?.split("T")[0] || "")
    setEditAbatementDate(c.abatement_date?.split("T")[0] || "")
  }

  const cancelEdit = () => {
    setEditCaseId(null)
    setEditNote("")
    setEditVerification("")
    setEditSelectedIcd(null)
    setEditIcdQuery("")
    setEditOnsetDate("")
    setEditAbatementDate("")
  }

  const handleEditSave = (caseId: string, clinicalStatus: string) => {
    updateData.mutate(
      {
        caseId,
        patientId,
        current_clinical_status: clinicalStatus,
        verification_status: editVerification || undefined,
        icd_code: editSelectedIcd?.code || undefined,
        icd_display: editSelectedIcd?.display || undefined,
        onset_date: editOnsetDate || undefined,
        abatement_date: editAbatementDate || undefined,
        note: editNote || undefined,
      },
      {
        onSuccess: () => {
          toast.success("Podaci slučaja ažurirani")
          cancelEdit()
        },
        onError: (err) => toast.error(err.message),
      },
    )
  }

  const getAvailableActions = (c: CaseItem) => {
    // State machine per Simplifier spec:
    //   active → remission(2.3), resolve(2.4)
    //   remission → relapse(2.5), resolve(2.4)
    //   relapse → remission(2.3), resolve(2.4)
    //   resolved → reopen(2.9)
    //   Delete (2.7) never shipped — product rule.
    const filter = (actions: string[]) =>
      CASE_ACTIONS.filter((a) => actions.includes(a.value))

    switch (c.clinical_status) {
      case "active":
      case "recurrence":
        return filter(["remission", "resolve"])
      case "remission":
        return filter(["relapse", "resolve"])
      case "relapse":
        return filter(["remission", "resolve"])
      case "resolved":
        return filter(["reopen"])
      case "inactive":
        return []
      default:
        return []
    }
  }

  const cases = casesQuery.data?.cases || []

  const { sorted: sortedCases, sortKey: cSortKey, sortDir: cSortDir, toggleSort: toggleCSort } = useTableSort<CaseItem>(cases, {
    defaultKey: "onset_date",
    defaultDir: "desc",
    keyAccessors: {
      status: (c) => CLINICAL_STATUS_LABELS[c.clinical_status] || c.clinical_status,
      verifikacija: (c) => VERIFICATION_STATUS_LABELS[c.verification_status || ""] || c.verification_status || "",
      icd_code: (c) => c.icd_code,
      naziv: (c) => c.icd_display,
      abatement_date: (c) => c.abatement_date || null,
      updated_at: (c) => c.updated_at || null,
    },
  })

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-lg flex items-center gap-2">
          <FileText className="h-5 w-5" />
          Upravljanje slučajevima
        </CardTitle>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger render={<Button size="sm" />}>
            <Plus className="h-4 w-4 mr-1" />
            Novi slučaj
          </DialogTrigger>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle>Kreiranje novog slučaja</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 pt-2">
              <div>
                <Label>MKB/ICD-10 šifra</Label>
                <Input
                  placeholder="Pretraži po šifri ili nazivu..."
                  value={icdQuery}
                  onChange={(e) => {
                    setIcdQuery(e.target.value)
                    setSelectedIcd(null)
                  }}
                />
                {icdSearch.data && icdSearch.data.length > 0 && !selectedIcd && (
                  <div className="mt-1 border rounded-md max-h-40 overflow-y-auto">
                    {icdSearch.data.map((item) => (
                      <button
                        key={item.code}
                        className="w-full text-left px-3 py-2 hover:bg-accent text-sm"
                        onClick={() => {
                          setSelectedIcd({ code: item.code, display: item.display })
                          setIcdQuery(`${item.code} — ${item.display}`)
                        }}
                      >
                        <span className="font-mono font-medium">{item.code}</span>{" "}
                        <span className="text-muted-foreground">{item.display}</span>
                      </button>
                    ))}
                  </div>
                )}
                {icdQuery.length >= 2 && !selectedIcd && icdSearch.data?.length === 0 && !icdSearch.isLoading && (
                  <div className="mt-1 space-y-2">
                    <p className="text-xs text-muted-foreground">Nema rezultata. Unesite ručno:</p>
                    <div className="flex gap-2">
                      <Input
                        className="w-28"
                        placeholder="Šifra (npr. J06.9)"
                        value={manualCode}
                        onChange={(e) => setManualCode(e.target.value.toUpperCase())}
                      />
                      <Input
                        className="flex-1"
                        placeholder="Naziv dijagnoze"
                        value={manualDisplay}
                        onChange={(e) => setManualDisplay(e.target.value)}
                      />
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={!manualCode || !manualDisplay}
                        onClick={() => {
                          setSelectedIcd({ code: manualCode, display: manualDisplay })
                          setIcdQuery(`${manualCode} — ${manualDisplay}`)
                          setManualCode("")
                          setManualDisplay("")
                        }}
                      >
                        Potvrdi
                      </Button>
                    </div>
                  </div>
                )}
                {selectedIcd && (
                  <Badge className="mt-1" variant="secondary">
                    {selectedIcd.code} — {selectedIcd.display}
                  </Badge>
                )}
              </div>
              <div>
                <Label>Datum početka</Label>
                <Input type="date" value={onsetDate} onChange={(e) => setOnsetDate(e.target.value)} />
              </div>
              <div>
                <Label>Status verifikacije</Label>
                <Select value={verification} onValueChange={(v) => v && setVerification(v)}>
                  <SelectTrigger>
                    <SelectValue>{VERIFICATION_STATUS_LABELS[verification] || verification}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {CEZIH_VERIFICATION_STATUSES.map((value) => (
                      <SelectItem key={value} value={value}>{VERIFICATION_STATUS_LABELS[value]}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground mt-1">
                  Zatvaranje slučaja moguće je samo za Potvrđen status.
                </p>
              </div>
              <div>
                <Label>Napomena (opcionalno)</Label>
                <Textarea
                  placeholder="Napomena o slučaju..."
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={3}
                />
              </div>
              <Button className="w-full" onClick={handleCreate} disabled={createCase.isPending || !selectedIcd}>
                {createCase.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Kreiraj slučaj
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </CardHeader>
      <CardContent>
        <div className="mb-3 rounded-md border border-blue-200 bg-blue-50 p-3 text-xs text-blue-900 space-y-1">
          <p className="font-medium">Kako koristiti:</p>
          <ul className="list-disc list-inside space-y-0.5">
            <li>
              <strong>Novi slučaj</strong> — upišite MKB šifru, datum početka i status verifikacije. Da bi mogli zatvoriti slučaj, on mora biti <em>Potvrđen</em>.
            </li>
            <li>
              Promjena stanja ide kroz <em>Akcija…</em> u desnoj koloni: Remisija, Relaps, Zatvori, Ponovno otvori ili Ponavljajući slučaj. Svaka zahtijeva digitalni potpis (kartica ili mobilna aplikacija).
            </li>
            <li>
              <strong>Zatvori</strong> je dostupan samo za slučajeve sa statusom verifikacije <em>Potvrđen</em>.
            </li>
          </ul>
        </div>
        {casesQuery.isLoading ? (
          <div className="flex justify-center py-4">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : casesQuery.isError ? (
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3">
            <p className="text-sm text-destructive">
              Greška pri dohvatu slučajeva: {(casesQuery.error as Error)?.message ?? "Nepoznata greška"}
            </p>
          </div>
        ) : cases.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">
            Nema pronađenih slučajeva za ovog pacijenta.
          </p>
        ) : (
          <div className="space-y-3">
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <SortableTableHead columnKey="status" label="Status" currentKey={cSortKey} currentDir={cSortDir} onSort={toggleCSort} className="w-[100px]" />
                    <SortableTableHead columnKey="verifikacija" label="Verifikacija" currentKey={cSortKey} currentDir={cSortDir} onSort={toggleCSort} className="w-[100px]" />
                    <SortableTableHead columnKey="icd_code" label="MKB šifra" currentKey={cSortKey} currentDir={cSortDir} onSort={toggleCSort} />
                    <SortableTableHead columnKey="naziv" label="Naziv" currentKey={cSortKey} currentDir={cSortDir} onSort={toggleCSort} />
                    <SortableTableHead columnKey="onset_date" label="Početak" currentKey={cSortKey} currentDir={cSortDir} onSort={toggleCSort} />
                    <SortableTableHead columnKey="updated_at" label="Izmjena" currentKey={cSortKey} currentDir={cSortDir} onSort={toggleCSort} />
                    <SortableTableHead columnKey="abatement_date" label="Završetak" currentKey={cSortKey} currentDir={cSortDir} onSort={toggleCSort} />
                    <TableHead className="w-[180px] text-right">Akcije</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sortedCases.map((c) => {
                    const actions = getAvailableActions(c)
                    return (
                      <TableRow key={c.case_id}>
                        <TableCell>
                          <Badge className={CLINICAL_STATUS_COLORS[c.clinical_status] || "bg-gray-100"}>
                            {CLINICAL_STATUS_LABELS[c.clinical_status] || c.clinical_status}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <span className="text-xs text-muted-foreground">
                            {VERIFICATION_STATUS_LABELS[c.verification_status || ""] || c.verification_status || "—"}
                          </span>
                        </TableCell>
                        <TableCell className="font-mono text-sm font-medium">{c.icd_code}</TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {c.icd_display}
                          {c.note && (
                            <span className="ml-1 text-xs text-blue-600" title={c.note}>
                              [bilješka]
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="text-sm">{formatDateTimeHR(c.onset_date)}</TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {c.updated_at ? formatDateTimeHR(c.updated_at) : "—"}
                        </TableCell>
                        <TableCell className="text-sm">{c.abatement_date ? formatDateTimeHR(c.abatement_date) : "—"}</TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1">
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-6 text-xs px-2"
                              onClick={() => startEdit(c)}
                              title="Izmijeni podatke slučaja (2.6)"
                            >
                              <Pencil className="h-3 w-3" />
                            </Button>
                            <Select
                              value=""
                              onValueChange={(action) => {
                                if (action) handleAction(c.case_id, action)
                              }}
                              disabled={updateStatus.isPending}
                            >
                              <SelectTrigger className="w-[120px] h-6 text-xs">
                                <SelectValue placeholder="Akcija..." />
                              </SelectTrigger>
                              <SelectContent>
                                {actions.map((a) => (
                                  <SelectItem key={a.value} value={a.value}>
                                    {a.label}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
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

      <Dialog open={!!editCaseId} onOpenChange={(open) => { if (!open) cancelEdit() }}>
        <DialogContent className="sm:max-w-[640px]">
          <DialogHeader>
            <DialogTitle>
              Izmjena slučaja
              {editCaseId && (
                <span className="ml-2 font-mono text-xs font-normal text-muted-foreground">{editCaseId}</span>
              )}
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Status verifikacije</Label>
              <Select value={editVerification} onValueChange={(v) => v && setEditVerification(v)}>
                <SelectTrigger className="h-8">
                  <SelectValue>{VERIFICATION_STATUS_LABELS[editVerification] || editVerification}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {CEZIH_VERIFICATION_STATUSES.map((val) => (
                    <SelectItem key={val} value={val}>{VERIFICATION_STATUS_LABELS[val]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Datum početka</Label>
              <Input type="date" className="h-8 text-sm" value={editOnsetDate} onChange={(e) => setEditOnsetDate(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Datum završetka</Label>
              <Input type="date" className="h-8 text-sm" value={editAbatementDate} onChange={(e) => setEditAbatementDate(e.target.value)} />
            </div>
            <div className="col-span-3 space-y-1">
              <Label className="text-xs">MKB/ICD-10 šifra</Label>
              <Input
                className="h-8 text-sm"
                placeholder="Pretraži po šifri ili nazivu..."
                value={editIcdQuery}
                onChange={(e) => {
                  setEditIcdQuery(e.target.value)
                  setEditSelectedIcd(null)
                }}
              />
              {editIcdSearch.data && editIcdSearch.data.length > 0 && !editSelectedIcd && (
                <div className="mt-1 border rounded-md max-h-32 overflow-y-auto">
                  {editIcdSearch.data.map((item) => (
                    <button
                      key={item.code}
                      className="w-full text-left px-3 py-1.5 hover:bg-accent text-sm"
                      onClick={() => {
                        setEditSelectedIcd({ code: item.code, display: item.display })
                        setEditIcdQuery(`${item.code} — ${item.display}`)
                      }}
                    >
                      <span className="font-mono font-medium">{item.code}</span>{" "}
                      <span className="text-muted-foreground">{item.display}</span>
                    </button>
                  ))}
                </div>
              )}
              {editSelectedIcd && (
                <Badge className="mt-1" variant="secondary">
                  {editSelectedIcd.code} — {editSelectedIcd.display}
                </Badge>
              )}
            </div>
            <div className="col-span-3 space-y-1">
              <Label className="text-xs">Napomena</Label>
              <Textarea
                value={editNote}
                onChange={(e) => setEditNote(e.target.value)}
                placeholder="Bilješka o slučaju..."
                className="min-h-24 text-sm"
              />
            </div>
          </div>
          <DialogFooter>
            <Button size="sm" variant="outline" onClick={cancelEdit}>Odustani</Button>
            <Button
              size="sm"
              disabled={updateData.isPending || !editCaseId}
              onClick={() => {
                if (!editCaseId) return
                const c = cases.find((x) => x.case_id === editCaseId)
                if (!c) return
                handleEditSave(editCaseId, c.clinical_status)
              }}
            >
              {updateData.isPending && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
              Spremi izmjene
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
