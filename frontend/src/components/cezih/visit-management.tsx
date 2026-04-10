"use client"

import { useState } from "react"
import { Plus, Loader2, Building2, ExternalLink } from "lucide-react"
import { toast } from "sonner"
import { formatDateTimeHR } from "@/lib/utils"
import { useAuth } from "@/lib/auth"

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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  useListVisits,
  useCreateVisit,
  useVisitAction,
} from "@/lib/hooks/use-cezih"
import type { VisitItem } from "@/lib/types"

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
  const { tenant } = useAuth()
  const { data: visitsData, isLoading } = useListVisits(patientMbo)
  const createVisit = useCreateVisit()
  const visitAction = useVisitAction()

  const [showCreate, setShowCreate] = useState(false)
  const [nacinPrijema, setNacinPrijema] = useState("6")
  const [reason, setReason] = useState("")
  const [actionVisitId, setActionVisitId] = useState<string | null>(null)

  const visits = visitsData?.visits ?? []
  const myOrgCode = tenant?.sifra_ustanove || ""

  const isOurVisit = (v: VisitItem) =>
    !!myOrgCode && v.service_provider_code === myOrgCode

  // Sort: our visits first, then by period_start descending
  const sortedVisits = [...visits].sort((a, b) => {
    const aOurs = isOurVisit(a) ? 0 : 1
    const bOurs = isOurVisit(b) ? 0 : 1
    if (aOurs !== bOurs) return aOurs - bOurs
    const aDate = a.period_start || ""
    const bDate = b.period_start || ""
    return bDate.localeCompare(aDate)
  })

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

  const getAvailableActions = (v: VisitItem) => {
    if (v.status === "entered-in-error" || v.status === "cancelled") return []
    if (!isOurVisit(v)) return [] // Can't act on other providers' visits
    if (v.status === "in-progress") return VISIT_ACTIONS.filter((a) => a.value === "close" || a.value === "storno")
    if (v.status === "finished") return VISIT_ACTIONS.filter((a) => a.value === "reopen" || a.value === "storno")
    return []
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <div className="flex items-center gap-2">
          <CardTitle className="text-base">Posjete</CardTitle>
          {visits.length > 0 && (
            <span className="text-xs text-muted-foreground">
              ({visits.filter(isOurVisit).length} naše / {visits.filter((v) => !isOurVisit(v)).length} ostale)
            </span>
          )}
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
                <Select value={nacinPrijema} onValueChange={(v) => v && setNacinPrijema(v)}>
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
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[100px]">Izvor</TableHead>
                  <TableHead className="w-[100px]">Status</TableHead>
                  <TableHead>Način prijema</TableHead>
                  <TableHead>Razlog</TableHead>
                  <TableHead>Početak</TableHead>
                  <TableHead>Kraj</TableHead>
                  <TableHead className="w-[100px] text-right">Akcije</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedVisits.map((v) => {
                  const ours = isOurVisit(v)
                  const actions = getAvailableActions(v)
                  return (
                    <TableRow
                      key={v.visit_id}
                      className={ours ? "" : "bg-muted/30"}
                    >
                      <TableCell>
                        {ours ? (
                          <Badge variant="default" className="bg-primary/90 text-xs gap-1">
                            <Building2 className="h-3 w-3" />
                            Naša
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="text-xs gap-1 text-muted-foreground">
                            <ExternalLink className="h-3 w-3" />
                            Vanjska
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary" className={VISIT_STATUS_COLORS[v.status] || ""}>
                          {VISIT_STATUS_LABELS[v.status] || v.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm">
                        {v.visit_type_display || NACIN_PRIJEMA_LABELS[v.visit_type] || v.visit_type}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {v.reason || "—"}
                      </TableCell>
                      <TableCell className="text-sm">
                        {v.period_start ? formatDateTimeHR(v.period_start) : "—"}
                      </TableCell>
                      <TableCell className="text-sm">
                        {v.period_end ? formatDateTimeHR(v.period_end) : "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        {actions.length > 0 && (
                          actionVisitId === v.visit_id ? (
                            <div className="flex justify-end gap-1 flex-wrap">
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
                            </div>
                          ) : (
                            <Button size="sm" variant="ghost" className="h-6 text-xs px-2" onClick={() => setActionVisitId(v.visit_id)}>
                              Akcije
                            </Button>
                          )
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
