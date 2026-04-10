"use client"

import { useState } from "react"
import { Plus, Loader2 } from "lucide-react"
import { toast } from "sonner"
import { formatDateTimeHR } from "@/lib/utils"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  useListVisits,
  useCreateVisit,
  useVisitAction,
} from "@/lib/hooks/use-cezih"

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

const VISIT_ACTIONS = [
  { value: "close", label: "Zatvori posjetu" },
  { value: "reopen", label: "Ponovno otvori" },
  { value: "storno", label: "Storniraj" },
]

interface VisitManagementProps {
  patientId: string
  patientMbo: string
}

export function VisitManagement({ patientId, patientMbo }: VisitManagementProps) {
  const { data: visitsData, isLoading } = useListVisits(patientMbo)
  const createVisit = useCreateVisit()
  const visitAction = useVisitAction()

  const [showCreate, setShowCreate] = useState(false)
  const [nacinPrijema, setNacinPrijema] = useState("6")
  const [reason, setReason] = useState("")
  const [actionVisitId, setActionVisitId] = useState<string | null>(null)

  const visits = visitsData?.visits ?? []

  const handleCreate = () => {
    createVisit.mutate(
      { patient_id: patientId, patient_mbo: patientMbo, nacin_prijema: nacinPrijema, reason: reason || undefined },
      {
        onSuccess: (res) => {
          toast.success(`Posjeta kreirana: ${res.visit_id}`)
          setShowCreate(false)
          setReason("")
        },
        onError: (err) => toast.error(err.message),
      },
    )
  }

  const handleAction = (visitId: string, action: string) => {
    visitAction.mutate(
      { visitId, action, patientMbo },
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

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <div className="flex items-center gap-2">
          <CardTitle className="text-base">Posjete</CardTitle>
        </div>
        <Button size="sm" variant="outline" onClick={() => setShowCreate(!showCreate)}>
          <Plus className="mr-1 h-3.5 w-3.5" />
          Nova posjeta
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {showCreate && (
          <div className="rounded-lg border p-3 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Vrsta posjete</Label>
                <Select value={nacinPrijema} onValueChange={setNacinPrijema}>
                  <SelectTrigger className="h-8">
                    <SelectValue placeholder="Odaberi vrstu">
                      {NACIN_PRIJEMA_LABELS[nacinPrijema] || nacinPrijema}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(NACIN_PRIJEMA_LABELS).map(([val, label]) => (
                      <SelectItem key={val} value={val}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Razlog (opcionalno)</Label>
                <Input
                  className="h-8 text-sm"
                  placeholder="Razlog posjete"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="outline" onClick={() => setShowCreate(false)}>Odustani</Button>
              <Button size="sm" onClick={handleCreate} disabled={createVisit.isPending}>
                {createVisit.isPending && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
                Kreiraj posjetu
              </Button>
            </div>
          </div>
        )}

        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
            <Loader2 className="h-4 w-4 animate-spin" />
            Učitavanje posjeta...
          </div>
        ) : visits.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">Nema posjeta za ovog pacijenta</p>
        ) : (
          <div className="space-y-2">
            {visits.map((v) => (
              <div key={v.visit_id} className="rounded-lg border p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className={VISIT_STATUS_COLORS[v.status] || ""}>
                      {VISIT_STATUS_LABELS[v.status] || v.status}
                    </Badge>
                    <Badge variant="outline">{NACIN_PRIJEMA_LABELS[v.visit_type] || v.visit_type}</Badge>
                    <span className="text-xs font-mono text-muted-foreground">{v.visit_id}</span>
                  </div>
                </div>
                {v.reason && (
                  <p className="text-sm text-muted-foreground">{v.reason}</p>
                )}
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <div>
                    {v.period_start && <span>Početak: {formatDateTimeHR(v.period_start)}</span>}
                    {v.period_end && <span className="ml-3">Kraj: {formatDateTimeHR(v.period_end)}</span>}
                  </div>
                  {v.status !== "entered-in-error" && v.status !== "cancelled" && (
                    <div className="flex gap-1">
                      {actionVisitId === v.visit_id ? (
                        <div className="flex gap-1">
                          {VISIT_ACTIONS.filter((a) => {
                            if (v.status === "in-progress") return a.value === "close" || a.value === "storno"
                            if (v.status === "finished") return a.value === "reopen" || a.value === "storno"
                            return false
                          }).map((a) => (
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
                            Odustani
                          </Button>
                        </div>
                      ) : (
                        <Button size="sm" variant="ghost" className="h-6 text-xs px-2" onClick={() => setActionVisitId(v.visit_id)}>
                          Akcije
                        </Button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
