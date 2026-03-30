"use client"

import { useState } from "react"
import { FileText, Plus, Loader2 } from "lucide-react"
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
  useRetrieveCases,
  useCreateCase,
  useUpdateCaseStatus,
  useCodeSystemQuery,
} from "@/lib/hooks/use-cezih"
import { MockBadge } from "./mock-badge"

const CLINICAL_STATUS_COLORS: Record<string, string> = {
  active: "bg-blue-100 text-blue-800",
  remission: "bg-green-100 text-green-800",
  relapse: "bg-orange-100 text-orange-800",
  resolved: "bg-gray-100 text-gray-800",
}

const CLINICAL_STATUS_LABELS: Record<string, string> = {
  active: "Aktivan",
  remission: "Remisija",
  relapse: "Relaps",
  resolved: "Zatvoren",
}

const CASE_ACTIONS = [
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

  const casesQuery = useRetrieveCases(patientMbo)
  const createCase = useCreateCase()
  const updateStatus = useUpdateCaseStatus()
  const icdSearch = useCodeSystemQuery("icd10-hr", icdQuery)

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

  const [pendingAction, setPendingAction] = useState<Record<string, string>>({})

  const handleAction = (caseId: string, action: string) => {
    const actionLabel = CASE_ACTIONS.find((a) => a.value === action)?.label || action
    updateStatus.mutate(
      { caseId, mbo: patientMbo, action },
      {
        onSuccess: () => {
          toast.success(`${actionLabel} — uspješno`)
          setPendingAction((prev) => ({ ...prev, [caseId]: "" }))
        },
        onError: (err) => toast.error(err.message),
      }
    )
  }

  const cases = casesQuery.data?.cases || []

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-lg flex items-center gap-2">
          <FileText className="h-5 w-5" />
          Upravljanje slučajevima
        </CardTitle>
        <div className="flex items-center gap-2">
          <MockBadge />
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger>
              <Button size="sm" disabled={!patientMbo}>
                <Plus className="h-4 w-4 mr-1" />
                Novi slučaj
              </Button>
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
                  {selectedIcd && (
                    <Badge className="mt-1" variant="secondary">
                      {selectedIcd.code} — {selectedIcd.display}
                    </Badge>
                  )}
                </div>
                <div>
                  <Label>Datum početka</Label>
                  <Input
                    type="date"
                    value={onsetDate}
                    onChange={(e) => setOnsetDate(e.target.value)}
                  />
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
                <Button
                  className="w-full"
                  onClick={handleCreate}
                  disabled={createCase.isPending || !selectedIcd}
                >
                  {createCase.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  Kreiraj slučaj
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </CardHeader>
      <CardContent>
        {casesQuery.isLoading ? (
          <div className="flex justify-center py-4">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : cases.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">
            {patientMbo
              ? "Nema pronađenih slučajeva za ovog pacijenta."
              : "Pacijent nema MBO — unesite MBO za pretragu slučajeva."}
          </p>
        ) : (
          <div className="space-y-3">
            {cases.map((c) => (
              <div
                key={c.case_id}
                className="flex items-center justify-between p-3 rounded-lg border"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <Badge className={CLINICAL_STATUS_COLORS[c.clinical_status] || "bg-gray-100"}>
                      {CLINICAL_STATUS_LABELS[c.clinical_status] || c.clinical_status}
                    </Badge>
                    <span className="font-mono text-sm font-medium">{c.icd_code}</span>
                    <span className="text-sm text-muted-foreground">{c.icd_display}</span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Od: {formatDateHR(c.onset_date)} | ID: {c.case_id}
                  </div>
                </div>
                <Select
                  value={pendingAction[c.case_id] || null}
                  onValueChange={(action) => {
                    if (action) {
                      setPendingAction((prev) => ({ ...prev, [c.case_id]: action as string }))
                      handleAction(c.case_id, action as string)
                    }
                  }}
                  disabled={updateStatus.isPending}
                >
                  <SelectTrigger className="w-[140px] h-8 text-xs">
                    <SelectValue placeholder="Akcija..." />
                  </SelectTrigger>
                  <SelectContent>
                    {CASE_ACTIONS.filter((a) => {
                      if (c.clinical_status === "resolved") return ["reopen", "delete"].includes(a.value)
                      if (c.clinical_status === "remission") return ["relapse", "resolve", "delete"].includes(a.value)
                      return ["remission", "relapse", "resolve", "delete"].includes(a.value)
                    }).map((a) => (
                      <SelectItem key={a.value} value={a.value}>
                        {a.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
