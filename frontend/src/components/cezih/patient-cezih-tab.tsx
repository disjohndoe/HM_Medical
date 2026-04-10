"use client"

import { useState } from "react"
import { Loader2, Shield, FileText, Trash2, RefreshCw, CheckCircle2, XCircle } from "lucide-react"
import { toast } from "sonner"

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
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { PrescriptionForm } from "@/components/prescriptions/prescription-form"
import { CaseManagement } from "@/components/cezih/case-management"
import { VisitManagement } from "@/components/cezih/visit-management"
import { usePatientCezihSummary, useInsuranceCheck, useCancelDocument, useReplaceDocument } from "@/lib/hooks/use-cezih"
import { usePermissions } from "@/lib/hooks/use-permissions"
import { OSIGURANJE_STATUS } from "@/lib/constants"
import { useRecordTypeMaps } from "@/lib/hooks/use-record-types"
import { formatDateTimeHR } from "@/lib/utils"

interface PatientCezihTabProps {
  patientId: string
  patientMbo: string | null
}

export function PatientCezihTab({ patientId, patientMbo }: PatientCezihTabProps) {
  const { data: summary, isLoading } = usePatientCezihSummary(patientId)
  const insuranceCheck = useInsuranceCheck()
  const cancelDocument = useCancelDocument()
  const replaceDocument = useReplaceDocument()
  const { canUseHzzo } = usePermissions()
  const { tipLabelMap } = useRecordTypeMaps()
  const [cezihSubTab, setCezihSubTab] = useState("posjete")
  const [eReceptOpen, setEReceptOpen] = useState(false)
  const [nalazStornoTarget, setNalazStornoTarget] = useState<string | null>(null)
  const [nalazReplaceTarget, setNalazReplaceTarget] = useState<string | null>(null)

  function handleCheckInsurance() {
    if (!patientMbo) {
      toast.error("Pacijent nema MBO")
      return
    }
    insuranceCheck.mutate(patientMbo, {
      onSuccess: () => toast.success("Osiguranje provjereno"),
      onError: (err: Error) => toast.error(err.message || "Greška pri provjeri osiguranja"),
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
                  disabled={insuranceCheck.isPending || !patientMbo}
                >
                  {insuranceCheck.isPending && <Loader2 className="mr-2 h-3 w-3 animate-spin" />}
                  Provjeri osiguranje
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

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
            <Button
              size="sm"
              variant="outline"
              onClick={handleCheckInsurance}
              disabled={insuranceCheck.isPending || !patientMbo}
            >
              <Shield className="mr-2 h-3 w-3" />
              Provjeri osiguranje
            </Button>
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
          {patientMbo ? (
            <VisitManagement patientId={patientId} patientMbo={patientMbo} onNavigateToCase={() => setCezihSubTab("slucajevi")} />
          ) : (
            <p className="text-sm text-muted-foreground py-4 text-center">
              Pacijent nema MBO — posjete nisu dostupne
            </p>
          )}
        </TabsContent>

        <TabsContent value="slucajevi">
          {patientMbo ? (
            <CaseManagement patientId={patientId} patientMbo={patientMbo} />
          ) : (
            <p className="text-sm text-muted-foreground py-4 text-center">
              Pacijent nema MBO — slučajevi nisu dostupni
            </p>
          )}
        </TabsContent>

        <TabsContent value="e-nalazi">
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
                  Nema poslanih e-Nalaza za ovog pacijenta
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Datum</TableHead>
                      <TableHead>Tip</TableHead>
                      <TableHead className="hidden sm:table-cell">Referenca</TableHead>
                      <TableHead className="hidden md:table-cell">Potpis</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Akcije</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {summary.e_nalaz_history.map((item) => (
                      <TableRow key={item.record_id}>
                        <TableCell className="text-sm">{formatDateTimeHR(item.datum)}</TableCell>
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
                          <Badge
                            variant="outline"
                            className={
                              item.cezih_storno
                                ? "bg-red-100 text-red-800 border-red-200"
                                : "bg-green-100 text-green-800 border-green-200"
                            }
                          >
                            {item.cezih_storno ? "Storniran" : "Poslan"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          {!item.cezih_storno && item.reference_id && (
                            <div className="flex justify-end gap-1">
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-8 w-8 p-0"
                                onClick={() => setNalazReplaceTarget(item.reference_id)}
                                title="Zamijeni e-Nalaz"
                              >
                                <RefreshCw className="h-3.5 w-3.5" />
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
                            </div>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
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
            onError: (err) => toast.error(err.message || "Greška pri stornu e-Nalaza"),
          })
        }}
        loading={cancelDocument.isPending}
      />

      {/* Replace e-Nalaz confirmation dialog */}
      <ConfirmDialog
        open={!!nalazReplaceTarget}
        onOpenChange={(open: boolean) => !open && setNalazReplaceTarget(null)}
        title="Zamjena e-Nalaza"
        description="Jeste li sigurni da želite zamijeniti ovaj dokument na CEZIH? Stari dokument će biti označen kao zamijenjen."
        confirmLabel="Zamijeni"
        onConfirm={() => {
          if (!nalazReplaceTarget) return
          replaceDocument.mutate(nalazReplaceTarget, {
            onSuccess: () => {
              toast.success("e-Nalaz zamijenjen")
              setNalazReplaceTarget(null)
            },
            onError: (err) => toast.error(err.message || "Greška pri zamjeni e-Nalaza"),
          })
        }}
        loading={replaceDocument.isPending}
      />
    </div>
  )
}
