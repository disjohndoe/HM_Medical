"use client"

import { useState } from "react"
import { Loader2, Shield, Pill, FileText } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Skeleton } from "@/components/ui/skeleton"
import { MockBadge } from "@/components/cezih/mock-badge"
import { EReceptDialog } from "@/components/cezih/e-recept-dialog"
import { VisitManagement } from "@/components/cezih/visit-management"
import { CaseManagement } from "@/components/cezih/case-management"
import { usePatientCezihSummary, useInsuranceCheck } from "@/lib/hooks/use-cezih"
import { OSIGURANJE_STATUS, RECORD_TIP } from "@/lib/constants"
import { formatDateTimeHR } from "@/lib/utils"

interface PatientCezihTabProps {
  patientId: string
  patientMbo: string | null
}

export function PatientCezihTab({ patientId, patientMbo }: PatientCezihTabProps) {
  const { data: summary, isLoading } = usePatientCezihSummary(patientId)
  const insuranceCheck = useInsuranceCheck()
  const [eReceptOpen, setEReceptOpen] = useState(false)

  const handleCheckInsurance = () => {
    if (!patientMbo) {
      toast.error("Pacijent nema MBO broj")
      return
    }
    insuranceCheck.mutate(patientMbo, {
      onSuccess: () => toast.success("Osiguranje provjereno"),
      onError: (err) => toast.error(err.message),
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
              <MockBadge />
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
            <Button
              size="sm"
              variant="outline"
              onClick={() => setEReceptOpen(true)}
            >
              <Pill className="mr-2 h-3 w-3" />
              Pošalji e-Recept
            </Button>
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

      {/* e-Nalaz history */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-sm font-medium">e-Nalaz povijest</CardTitle>
            <MockBadge />
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
                  <TableHead>Poslano</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {summary.e_nalaz_history.map((item) => (
                  <TableRow key={item.record_id}>
                    <TableCell className="text-sm">{formatDateTimeHR(item.datum)}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs">
                        {RECORD_TIP[item.tip] || item.tip}
                      </Badge>
                    </TableCell>
                    <TableCell className="hidden sm:table-cell font-mono text-xs">
                      {item.reference_id || "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {item.cezih_sent_at ? formatDateTimeHR(item.cezih_sent_at) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* e-Recept history */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div className="flex items-center gap-2">
            <Pill className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-sm font-medium">e-Recept povijest</CardTitle>
            <MockBadge />
          </div>
        </CardHeader>
        <CardContent>
          {!summary?.e_recept_history.length ? (
            <p className="text-sm text-muted-foreground text-center py-4">
              Nema poslanih e-Recepta za ovog pacijenta
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Datum</TableHead>
                  <TableHead>ID recepta</TableHead>
                  <TableHead>Lijekovi</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {summary.e_recept_history.map((item) => (
                  <TableRow key={item.recept_id}>
                    <TableCell className="text-sm">{formatDateTimeHR(item.datum)}</TableCell>
                    <TableCell className="font-mono text-xs">{item.recept_id}</TableCell>
                    <TableCell className="text-sm max-w-[200px] truncate">
                      {item.lijekovi.join(", ") || "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Visit & Case Management */}
      {patientMbo && (
        <>
          <VisitManagement patientId={patientId} patientMbo={patientMbo} />
          <CaseManagement patientId={patientId} patientMbo={patientMbo} />
        </>
      )}

      <EReceptDialog
        open={eReceptOpen}
        onOpenChange={setEReceptOpen}
        patientId={patientId}
      />
    </div>
  )
}
