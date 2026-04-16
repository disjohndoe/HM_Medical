"use client"

import { useState } from "react"
import { FileText, Plus, Loader2, Pencil } from "lucide-react"
import { toast } from "sonner"
import { formatDateHR } from "@/lib/utils"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
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

const CASE_ACTIONS = [
  { value: "create_recurring", label: "Ponavljajući slučaj" },
  { value: "remission", label: "Remisija" },
  { value: "relapse", label: "Relaps" },
  { value: "resolve", label: "Zatvori" },
  { value: "reopen", label: "Ponovno otvori" },
  { value: "delete", label: "Obriši" },
]

interface CaseManagementProps {
  patientId: string
  patientMbo: string
}

export function CaseManagement({ patientId, patientMbo }: CaseManagementProps) {
  const [createOpen, setCreateOpen] = useState(false)
  const [icdQuery, setIcdQuery] = useState("")
  const [selectedIcd, setSelectedIcd] = useState<{ code: string; display: string } | null>(null)
  const [onsetDate, setOnsetDate] = useState(new Date().toISOString().split("T")[0])
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

  const casesQuery = useRetrieveCases(patientMbo)
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
        patient_mbo: patientMbo,
        icd_code: selectedIcd.code,
        icd_display: selectedIcd.display,
        onset_date: onsetDate,
        note: note || undefined,
      },
      {
        onSuccess: (data) => {
          toast.success(`Slučaj kreiran: ${data.cezih_case_id || data.local_case_id}`)
          setCreateOpen(false)
          setSelectedIcd(null)
          setIcdQuery("")
          setNote("")
        },
        onError: (err) => toast.error(err.message),
      }
    )
  }

  const handleAction = (caseId: string, action: string) => {
    const actionLabel = CASE_ACTIONS.find((a) => a.value === action)?.label || action
    updateStatus.mutate(
      { caseId, mbo: patientMbo, action },
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
        mbo: patientMbo,
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
    switch (c.clinical_status) {
      case "active":
      case "recurrence":
        return CASE_ACTIONS.filter((a) => ["create_recurring", "remission", "resolve", "delete"].includes(a.value))
      case "remission":
        return CASE_ACTIONS.filter((a) => ["relapse", "resolve", "delete"].includes(a.value))
      case "relapse":
        return CASE_ACTIONS.filter((a) => ["remission", "resolve", "delete"].includes(a.value))
      case "resolved":
      case "inactive":
        return CASE_ACTIONS.filter((a) => ["reopen", "delete"].includes(a.value))
      default:
        return CASE_ACTIONS.filter((a) => a.value === "delete")
    }
  }

  const cases = casesQuery.data?.cases || []

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-lg flex items-center gap-2">
          <FileText className="h-5 w-5" />
          Upravljanje slučajevima
        </CardTitle>
        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger render={<Button size="sm" disabled={!patientMbo} />}>
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
            {patientMbo
              ? "Nema pronađenih slučajeva za ovog pacijenta."
              : "Pacijent nema MBO — unesite MBO za pretragu slučajeva."}
          </p>
        ) : (
          <div className="space-y-3">
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[100px]">Status</TableHead>
                    <TableHead className="w-[100px]">Verifikacija</TableHead>
                    <TableHead>MKB šifra</TableHead>
                    <TableHead>Naziv</TableHead>
                    <TableHead>Početak</TableHead>
                    <TableHead>Završetak</TableHead>
                    <TableHead className="w-[180px] text-right">Akcije</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {cases.map((c) => {
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
                        <TableCell className="text-sm">{formatDateHR(c.onset_date)}</TableCell>
                        <TableCell className="text-sm">{c.abatement_date ? formatDateHR(c.abatement_date) : "—"}</TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1">
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-6 text-xs px-2"
                              onClick={() => editCaseId === c.case_id ? cancelEdit() : startEdit(c)}
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

            {/* Edit form — shown below table */}
            {editCaseId && (() => {
              const c = cases.find((x) => x.case_id === editCaseId)
              if (!c) return null
              return (
                <div className="rounded-lg border p-3 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">Izmjena slučaja: <span className="font-mono text-xs text-muted-foreground">{editCaseId}</span></span>
                    <Button size="sm" variant="ghost" className="h-6 text-xs px-2" onClick={cancelEdit}>×</Button>
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    <div className="space-y-1">
                      <Label className="text-xs">Status verifikacije</Label>
                      <Select value={editVerification} onValueChange={(v) => v && setEditVerification(v)}>
                        <SelectTrigger className="h-8">
                          <SelectValue>{VERIFICATION_STATUS_LABELS[editVerification] || editVerification}</SelectValue>
                        </SelectTrigger>
                        <SelectContent>
                          {Object.entries(VERIFICATION_STATUS_LABELS).map(([val, label]) => (
                            <SelectItem key={val} value={val}>{label}</SelectItem>
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
                        className="min-h-[50px] text-sm"
                      />
                    </div>
                  </div>
                  <div className="flex justify-end gap-2">
                    <Button size="sm" variant="outline" onClick={cancelEdit}>Odustani</Button>
                    <Button size="sm" disabled={updateData.isPending} onClick={() => handleEditSave(editCaseId, c.clinical_status)}>
                      {updateData.isPending && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
                      Spremi izmjene
                    </Button>
                  </div>
                </div>
              )
            })()}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
