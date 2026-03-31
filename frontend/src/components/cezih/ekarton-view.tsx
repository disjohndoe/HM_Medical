"use client"

import { useState } from "react"
import {
  AlertTriangle,
  Download,
  FileText,
  Loader2,
  Pill,
  Shield,
  Stethoscope,
} from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { MockBadge } from "@/components/cezih/mock-badge"
import {
  usePatientCezihSummary,
  useRetrieveCases,
  useRetrieveDocument,
  useInsuranceCheck,
} from "@/lib/hooks/use-cezih"
import { OSIGURANJE_STATUS, RECORD_TIP } from "@/lib/constants"
import { formatDateTimeHR } from "@/lib/utils"

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

interface EkartonViewProps {
  patientId: string
  patientMbo: string | null
  alergije: string | null
  fetchTime: string | null
}

export function EkartonView({ patientId, patientMbo, alergije, fetchTime }: EkartonViewProps) {
  const { data: summary, isLoading } = usePatientCezihSummary(patientId)
  const casesQuery = useRetrieveCases(patientMbo ?? "")
  const retrieveDoc = useRetrieveDocument()
  const insuranceCheck = useInsuranceCheck()

  const handleCheckInsurance = () => {
    if (!patientMbo) return
    insuranceCheck.mutate(patientMbo, {
      onSuccess: () => toast.success("Osiguranje provjereno"),
      onError: (err) => toast.error(err.message),
    })
  }

  const handleDownloadPdf = (referenceId: string) => {
    retrieveDoc.mutate(referenceId, {
      onSuccess: (blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement("a")
        a.href = url
        a.download = `e-nalaz-${referenceId}.pdf`
        a.click()
        URL.revokeObjectURL(url)
      },
      onError: () => toast.error("Greška pri preuzimanju dokumenta"),
    })
  }

  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-6 space-y-4">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </CardContent>
      </Card>
    )
  }

  const insurance = summary?.insurance
  const cases = casesQuery.data?.cases || []
  const eNalazHistory = summary?.e_nalaz_history || []
  const eReceptHistory = summary?.e_recept_history || []
  const statusConfig = insurance?.status_osiguranja
    ? OSIGURANJE_STATUS[insurance.status_osiguranja]
    : null

  const activeCases = cases.filter((c) => c.clinical_status !== "resolved")

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="text-lg flex items-center gap-2">
          <FileText className="h-5 w-5" />
          e-Karton iz CEZIH-a
        </CardTitle>
        <MockBadge />
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Osiguranje */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <Shield className="h-4 w-4" />
            Osiguranje
          </div>
          {insurance?.status_osiguranja ? (
            <div className="flex items-center gap-2 flex-wrap">
              <Badge className={statusConfig?.color || ""}>
                {statusConfig?.label || insurance.status_osiguranja}
              </Badge>
              {insurance.osiguravatelj && (
                <span className="text-sm">{insurance.osiguravatelj}</span>
              )}
              <span className="text-xs text-muted-foreground">
                · Provjereno {fetchTime ? formatDateTimeHR(fetchTime) : insurance.last_checked ? formatDateTimeHR(insurance.last_checked) : ""}
              </span>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Nije provjereno</span>
              <Button
                size="sm"
                variant="outline"
                onClick={handleCheckInsurance}
                disabled={insuranceCheck.isPending || !patientMbo}
              >
                {insuranceCheck.isPending && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
                Provjeri
              </Button>
            </div>
          )}
        </div>

        <Separator />

        {/* Alergije */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <AlertTriangle className="h-4 w-4" />
            Alergije
          </div>
          {alergije ? (
            <div className="rounded-md bg-red-50 border border-red-200 px-3 py-2">
              <p className="text-sm font-medium text-red-800">{alergije}</p>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Nema zabilježenih alergija</p>
          )}
        </div>

        <Separator />

        {/* Aktivne dijagnoze */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <Stethoscope className="h-4 w-4" />
            Aktivne dijagnoze
            {activeCases.length > 0 && (
              <Badge variant="outline" className="text-xs ml-1">
                {activeCases.length}
              </Badge>
            )}
          </div>
          {casesQuery.isLoading ? (
            <div className="flex justify-center py-2">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : !patientMbo ? (
            <p className="text-sm text-muted-foreground">Nema MBO — dohvat nije moguć</p>
          ) : activeCases.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nema aktivnih dijagnoza</p>
          ) : (
            <div className="space-y-1.5">
              {activeCases.map((c) => (
                <div key={c.case_id} className="flex items-center gap-2">
                  <Badge className={CLINICAL_STATUS_COLORS[c.clinical_status] || "bg-gray-100"}>
                    {CLINICAL_STATUS_LABELS[c.clinical_status] || c.clinical_status}
                  </Badge>
                  <span className="font-mono text-sm">{c.icd_code}</span>
                  <span className="text-sm text-muted-foreground">{c.icd_display}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <Separator />

        {/* Tekuća terapija */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <Pill className="h-4 w-4" />
            Tekuća terapija
            {eReceptHistory.length > 0 && (
              <Badge variant="outline" className="text-xs ml-1">
                {eReceptHistory.length}
              </Badge>
            )}
          </div>
          {eReceptHistory.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nema podataka o terapiji</p>
          ) : (
            <div className="space-y-1.5">
              {eReceptHistory.map((r) => (
                <div key={r.recept_id} className="flex items-center justify-between">
                  <div className="text-sm">
                    <span>{r.lijekovi.join(", ")}</span>
                  </div>
                  <span className="text-xs text-muted-foreground whitespace-nowrap ml-2">
                    {formatDateTimeHR(r.datum)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <Separator />

        {/* Povijest e-Nalaza */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <FileText className="h-4 w-4" />
            Povijest e-Nalaza
            {eNalazHistory.length > 0 && (
              <Badge variant="outline" className="text-xs ml-1">
                {eNalazHistory.length}
              </Badge>
            )}
          </div>
          {eNalazHistory.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nema poslanih e-Nalaza</p>
          ) : (
            <div className="space-y-1.5">
              {eNalazHistory.map((n) => (
                <div key={n.record_id} className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <Badge
                      variant="outline"
                      className={
                        n.cezih_storno
                          ? "bg-red-100 text-red-800 border-red-200"
                          : "bg-green-100 text-green-800 border-green-200"
                      }
                    >
                      {n.cezih_storno ? "Storniran" : "Poslan"}
                    </Badge>
                    <span className="text-sm text-muted-foreground">
                      {RECORD_TIP[n.tip] || n.tip}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {formatDateTimeHR(n.datum)}
                    </span>
                  </div>
                  {n.reference_id && !n.cezih_storno && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0 shrink-0"
                      onClick={() => handleDownloadPdf(n.reference_id!)}
                      disabled={retrieveDoc.isPending}
                      title="Preuzmi PDF"
                    >
                      <Download className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
