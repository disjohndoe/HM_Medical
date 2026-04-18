"use client"

import { useEffect, useRef, useState } from "react"
import {
  AlertTriangle,
  Calendar,
  CheckCircle2,
  Download,
  FileSearch,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  usePatientCezihSummary,
  useRetrieveCases,
  useRetrieveDocument,
  useListVisits,
  useDocumentSearch,
  useInsuranceCheck,
} from "@/lib/hooks/use-cezih"
import { OSIGURANJE_STATUS, ICD_CHAPTERS } from "@/lib/constants"
import { useRecordTypeMaps } from "@/lib/hooks/use-record-types"
import { formatDateHR, formatDateTimeHR } from "@/lib/utils"

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

const VISIT_STATUS_COLORS: Record<string, string> = {
  "in-progress": "bg-blue-100 text-blue-800",
  finished: "bg-green-100 text-green-800",
  planned: "bg-amber-100 text-amber-800",
  cancelled: "bg-gray-100 text-gray-800",
  "entered-in-error": "bg-red-100 text-red-800",
}

const VISIT_STATUS_LABELS: Record<string, string> = {
  "in-progress": "U tijeku",
  finished: "Završena",
  planned: "Planirana",
  cancelled: "Otkazana",
  "entered-in-error": "Pogreška",
}

const DOC_STATUS_COLORS: Record<string, string> = {
  current: "bg-green-100 text-green-800",
  superseded: "bg-gray-100 text-gray-800",
  "entered-in-error": "bg-red-100 text-red-800",
  Otvorena: "bg-green-100 text-green-800",
  Zatvorena: "bg-gray-100 text-gray-800",
  Pogreška: "bg-red-100 text-red-800",
}

function matchesIcdFilter(code: string, prefixStr: string): boolean {
  if (!prefixStr) return true
  const prefixes = prefixStr.split(",")
  return prefixes.some((p) => code.startsWith(p))
}

interface EkartonViewProps {
  patientId: string
  hasCezihIdentifier: boolean
  alergije: string | null
}

export function EkartonView({ patientId, hasCezihIdentifier, alergije }: EkartonViewProps) {
  const { data: summary, isLoading } = usePatientCezihSummary(patientId)
  const casesQuery = useRetrieveCases(hasCezihIdentifier ? patientId : "")
  const visitsQuery = useListVisits(hasCezihIdentifier ? patientId : "")
  const docsQuery = useDocumentSearch({ patient_id: hasCezihIdentifier ? patientId : undefined })
  const retrieveDoc = useRetrieveDocument()
  const insuranceMutation = useInsuranceCheck()
  const { tipLabelMap } = useRecordTypeMaps()

  // ICD filter — persisted in localStorage
  const [icdFilter, setIcdFilter] = useState(() => {
    if (typeof window === "undefined") return ""
    return localStorage.getItem("ekarton-icd-filter") || ""
  })

  const handleIcdFilterChange = (value: string | null) => {
    const v = !value || value === "__all__" ? "" : value
    setIcdFilter(v)
    localStorage.setItem("ekarton-icd-filter", v)
  }

  // Auto-check insurance on mount only if no fresh cached data (< 30 min)
  const didAutoCheck = useRef(false)
  useEffect(() => {
    if (didAutoCheck.current || !hasCezihIdentifier) return
    const lastChecked = summary?.insurance?.last_checked
    if (lastChecked) {
      const ageMinutes = (Date.now() - new Date(lastChecked).getTime()) / 60000
      if (ageMinutes < 30) {
        didAutoCheck.current = true
        return // cached result is fresh enough
      }
    }
    // If summary hasn't loaded yet, skip — this effect will re-run when it does
    if (!summary) return
    didAutoCheck.current = true
    insuranceMutation.mutate(patientId)
  }, [hasCezihIdentifier, patientId, summary?.insurance?.last_checked])

  const handleCheckInsurance = () => {
    if (!hasCezihIdentifier) return
    insuranceMutation.mutate(patientId)
  }

  const handleDownloadPdf = (referenceId: string, contentUrl?: string) => {
    retrieveDoc.mutate({ id: referenceId, contentUrl }, {
      onSuccess: (blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement("a")
        a.href = url
        a.download = `e-nalaz-${referenceId}.pdf`
        a.click()
        URL.revokeObjectURL(url)
      },
      onError: (err: Error) => toast.error(err.message || "Greška pri preuzimanju dokumenta"),
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
  const insData = insuranceMutation.data
  const insPending = insuranceMutation.isPending
  const insError = insuranceMutation.error
  const cases = casesQuery.data?.cases || []
  const visits = visitsQuery.data?.visits || []
  const documents = docsQuery.data || []
  const eNalazHistory = summary?.e_nalaz_history || []
  const eReceptHistory = summary?.e_recept_history || []
  const statusConfig = insurance?.status_osiguranja
    ? OSIGURANJE_STATUS[insurance.status_osiguranja]
    : null

  const activeCases = cases.filter((c) => c.clinical_status !== "resolved")
  const filteredCases = activeCases.filter((c) => matchesIcdFilter(c.icd_code, icdFilter))
  const activeVisits = visits
    .filter((v) => v.status === "in-progress" || v.status === "planned")
    .sort((a, b) => (b.period_start ?? "").localeCompare(a.period_start ?? ""))

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <CardTitle className="text-lg flex items-center gap-2">
          <FileText className="h-5 w-5" />
          e-Karton iz CEZIH-a
          {summary?.identifier_label && (
            <Badge variant="outline" className="text-xs font-normal" title="Identifikator korišten za dohvat iz CEZIH-a">
              {summary.identifier_label}
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* 1. Osiguranje */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <Shield className="h-4 w-4" />
            Osiguranje
          </div>
          {insPending ? (
            <div className="flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Provjera osiguranja...</span>
            </div>
          ) : insError ? (
            <div className="flex items-center gap-2 flex-wrap">
              <Badge className="bg-red-100 text-red-800">Greška</Badge>
              <span className="text-sm text-muted-foreground">{insError.message}</span>
              <Button size="sm" variant="outline" onClick={handleCheckInsurance} disabled={!hasCezihIdentifier}>
                Pokušaj ponovo
              </Button>
            </div>
          ) : insData?.status_osiguranja ? (
            <div className="flex items-center gap-2 flex-wrap">
              <Badge className={OSIGURANJE_STATUS[insData.status_osiguranja]?.color || "bg-gray-100 text-gray-800"}>
                {OSIGURANJE_STATUS[insData.status_osiguranja]?.label || insData.status_osiguranja}
              </Badge>
              {insData.osiguravatelj && (
                <span className="text-sm">{insData.osiguravatelj}</span>
              )}
              {insData.oib && (
                <span className="text-sm font-mono">OIB: {insData.oib}</span>
              )}
              <span className="text-xs text-muted-foreground">· Upravo provjereno</span>
              <Button size="sm" variant="ghost" className="h-6 text-xs px-2" onClick={handleCheckInsurance}>
                Osvježi
              </Button>
            </div>
          ) : insurance?.status_osiguranja ? (
            <div className="flex items-center gap-2 flex-wrap">
              <Badge className={statusConfig?.color || "bg-gray-100 text-gray-800"}>
                {statusConfig?.label || insurance.status_osiguranja}
              </Badge>
              {insurance.osiguravatelj && (
                <span className="text-sm">{insurance.osiguravatelj}</span>
              )}
              {insurance.broj_osiguranja && (
                <span className="text-sm font-mono">{insurance.broj_osiguranja}</span>
              )}
              <span className="text-xs text-muted-foreground">
                {insurance.last_checked && `· Provjereno ${formatDateTimeHR(insurance.last_checked)}`}
              </span>
              <Button size="sm" variant="ghost" className="h-6 text-xs px-2" onClick={handleCheckInsurance}>
                Osvježi
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Nije provjereno</span>
              <Button size="sm" variant="outline" onClick={handleCheckInsurance} disabled={insPending || !hasCezihIdentifier}>
                Provjeri
              </Button>
            </div>
          )}
        </div>

        <Separator />

        {/* 2. Alergije */}
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

        {/* 3. Aktivne dijagnoze — with ICD chapter filter */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <Stethoscope className="h-4 w-4" />
              Aktivne dijagnoze
              {activeCases.length > 0 && (
                <Badge variant="outline" className="text-xs ml-1">
                  {icdFilter ? `${filteredCases.length}/${activeCases.length}` : activeCases.length}
                </Badge>
              )}
            </div>
            {activeCases.length > 0 && (
              <Select value={icdFilter || "__all__"} onValueChange={handleIcdFilterChange}>
                <SelectTrigger className="h-7 w-[180px] text-xs">
                  <SelectValue placeholder="Sve dijagnoze">
                    {ICD_CHAPTERS.find((ch) => (ch.prefix || "__all__") === (icdFilter || "__all__"))?.label || "Sve dijagnoze"}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {ICD_CHAPTERS.map((ch) => (
                    <SelectItem key={ch.prefix || "__all__"} value={ch.prefix || "__all__"} className="text-xs">
                      {ch.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
          {casesQuery.isLoading ? (
            <div className="flex justify-center py-2">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : !hasCezihIdentifier ? (
            <p className="text-sm text-muted-foreground">Nema CEZIH identifikatora — dohvat nije moguć</p>
          ) : filteredCases.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {icdFilter && activeCases.length > 0 ? "Nema dijagnoza za odabrano područje" : "Nema aktivnih dijagnoza"}
            </p>
          ) : (
            <div className="space-y-1.5">
              {filteredCases.map((c) => (
                <div key={c.case_id} className="flex items-center gap-2 flex-wrap">
                  <Badge className={CLINICAL_STATUS_COLORS[c.clinical_status] || "bg-gray-100"}>
                    {CLINICAL_STATUS_LABELS[c.clinical_status] || c.clinical_status}
                  </Badge>
                  <span className="font-mono text-sm">{c.icd_code}</span>
                  <span className="text-sm text-muted-foreground">{c.icd_display}</span>
                  {c.onset_date && (
                    <span className="text-xs text-muted-foreground">· od {formatDateHR(c.onset_date)}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <Separator />

        {/* 4. Aktivne posjete */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <Calendar className="h-4 w-4" />
            Aktivne posjete
            {activeVisits.length > 0 && (
              <Badge variant="outline" className="text-xs ml-1">
                {activeVisits.length}
              </Badge>
            )}
          </div>
          {visitsQuery.isLoading ? (
            <div className="flex justify-center py-2">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : !hasCezihIdentifier ? (
            <p className="text-sm text-muted-foreground">Nema CEZIH identifikatora — dohvat nije moguć</p>
          ) : activeVisits.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nema aktivnih posjeta</p>
          ) : (
            <div className="space-y-1.5">
              {activeVisits.map((v) => {
                const label =
                  v.reason ||
                  v.tip_posjete_display ||
                  v.vrsta_posjete_display ||
                  v.visit_type_display ||
                  "Posjeta"
                return (
                  <div key={v.visit_id} className="flex items-center gap-2 flex-wrap">
                    <Badge className={VISIT_STATUS_COLORS[v.status] || "bg-gray-100"}>
                      {VISIT_STATUS_LABELS[v.status] || v.status}
                    </Badge>
                    <span className="text-sm">{label}</span>
                    {v.period_start && (
                      <span className="text-xs text-muted-foreground">
                        {formatDateTimeHR(v.period_start)}
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        <Separator />

        {/* 5. CEZIH dokumenti */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <FileSearch className="h-4 w-4" />
            CEZIH dokumenti
            {documents.length > 0 && (
              <Badge variant="outline" className="text-xs ml-1">
                {documents.length}
              </Badge>
            )}
          </div>
          {docsQuery.isLoading ? (
            <div className="flex justify-center py-2">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : !hasCezihIdentifier ? (
            <p className="text-sm text-muted-foreground">Nema CEZIH identifikatora — dohvat nije moguć</p>
          ) : documents.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nema CEZIH dokumenata</p>
          ) : (
            <div className="space-y-1.5">
              {documents.map((d) => (
                <div key={d.id} className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0 flex-wrap">
                    <Badge className={DOC_STATUS_COLORS[d.status] || "bg-gray-100"}>
                      {d.status}
                    </Badge>
                    <span className="text-sm truncate">{d.svrha}</span>
                    {d.izdavatelj && (
                      <span className="text-xs text-muted-foreground">{d.izdavatelj}</span>
                    )}
                    {d.datum_izdavanja && (
                      <span className="text-xs text-muted-foreground">{formatDateHR(d.datum_izdavanja)}</span>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0 shrink-0"
                    onClick={() => handleDownloadPdf(d.id, d.content_url)}
                    disabled={retrieveDoc.isPending}
                    title="Preuzmi PDF"
                  >
                    <Download className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>

        <Separator />

        {/* 6. Tekuća terapija */}
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

        {/* 7. Povijest e-Nalaza */}
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
                      {tipLabelMap[n.tip] || n.tip}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {formatDateTimeHR(n.datum)}
                    </span>
                    {n.cezih_signed && (
                      <div className="flex items-center gap-1" title={`Potpisano: ${formatDateTimeHR(n.cezih_signed_at || "")}`}>
                        <CheckCircle2 className="h-3 w-3 text-green-600" />
                      </div>
                    )}
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
