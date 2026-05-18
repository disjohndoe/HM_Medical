"use client"

import { useEffect, useRef, useState } from "react"
import {
  AlertTriangle,
  Calendar,
  CheckCircle2,
  Download,
  FileSearch,
  FileText,
  FolderDown,
  Globe,
  Loader2,
  Pill,
  Shield,
  Stethoscope,
} from "lucide-react"

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
import { TablePagination } from "@/components/shared/table-pagination"
import {
  usePatientCezihSummary,
  useRetrieveCases,
  useRetrieveDocument,
  useListVisits,
  useDocumentSearch,
  useInsuranceCheck,
} from "@/lib/hooks/use-cezih"
import { useDocuments, useImportCezihDocument } from "@/lib/hooks/use-documents"
import {
  OSIGURANJE_STATUS,
  ICD_CHAPTERS,
  COUNTRY_HR,
  CLINICAL_STATUS,
  CLINICAL_STATUS_COLORS,
  CLINICAL_STATUS_FILTER_OPTIONS,
  VISIT_STATUS_FILTER_OPTIONS,
  E_NALAZ_FILTER_OPTIONS,
} from "@/lib/constants"
import { isForeignPatient, type Patient } from "@/lib/types"
import { useRecordTypeMaps } from "@/lib/hooks/use-record-types"
import { formatDateHR, formatDateTimeHR } from "@/lib/utils"


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
  patient: Patient
  hasCezihIdentifier: boolean
  alergije: string | null
}

export function EkartonView({ patientId, patient, hasCezihIdentifier, alergije }: EkartonViewProps) {
  const isForeign = isForeignPatient(patient)
  const { data: summary, isLoading } = usePatientCezihSummary(patientId)
  const casesQuery = useRetrieveCases(hasCezihIdentifier ? patientId : "")
  const visitsQuery = useListVisits(hasCezihIdentifier ? patientId : "")
  const docsQuery = useDocumentSearch({ patient_id: hasCezihIdentifier ? patientId : undefined })
  const retrieveDoc = useRetrieveDocument()
  const insuranceMutation = useInsuranceCheck()
  const { tipLabelMap } = useRecordTypeMaps()
  const { data: localDocs } = useDocuments(patientId)
  const importCezih = useImportCezihDocument()

  const savedCezihRefIds = new Set(
    (localDocs || []).map((d) => d.cezih_reference_id).filter(Boolean)
  )

  // ICD filter — persisted in localStorage
  const [icdFilter, setIcdFilter] = useState(() => {
    if (typeof window === "undefined") return ""
    return localStorage.getItem("ekarton-icd-filter") || ""
  })

  const handleIcdFilterChange = (value: string | null) => {
    const v = !value || value === "__all__" ? "" : value
    setIcdFilter(v)
    localStorage.setItem("ekarton-icd-filter", v)
    setCasesPage(0)
  }

  // Status filters — persisted in localStorage. Defaults preserve the
  // pre-filter UX (Aktivne / Aktualne / Sve) so nothing changes for a
  // user who never touches the dropdowns.
  const [casesStatusFilter, setCasesStatusFilter] = useState(() => {
    if (typeof window === "undefined") return "active"
    return localStorage.getItem("ekarton-cases-status") || "active"
  })
  const [visitsStatusFilter, setVisitsStatusFilter] = useState(() => {
    if (typeof window === "undefined") return "open"
    return localStorage.getItem("ekarton-visits-status") || "open"
  })
  const [findingsStatusFilter, setFindingsStatusFilter] = useState(() => {
    if (typeof window === "undefined") return "all"
    return localStorage.getItem("ekarton-findings-status") || "all"
  })

  // Pagination state — 0-indexed, 10 per page. Not persisted across reloads.
  const [casesPage, setCasesPage] = useState(0)
  const [visitsPage, setVisitsPage] = useState(0)
  const [findingsPage, setFindingsPage] = useState(0)
  const PAGE_SIZE = 10

  const handleCasesStatusChange = (value: string | null) => {
    const v = value || "all"
    setCasesStatusFilter(v)
    localStorage.setItem("ekarton-cases-status", v)
    setCasesPage(0)
  }
  const handleVisitsStatusChange = (value: string | null) => {
    const v = value || "all"
    setVisitsStatusFilter(v)
    localStorage.setItem("ekarton-visits-status", v)
    setVisitsPage(0)
  }
  const handleFindingsStatusChange = (value: string | null) => {
    const v = value || "all"
    setFindingsStatusFilter(v)
    localStorage.setItem("ekarton-findings-status", v)
    setFindingsPage(0)
  }

  // Auto-check insurance on mount only if no fresh cached data (< 30 min).
  // Skipped entirely for foreign patients — they don't have HZZO coverage,
  // and CEZIH's PDQm for jedinstveni-id is flaky (HAPI-1361 / NoHttpResponseException).
  const didAutoCheck = useRef(false)
  useEffect(() => {
    if (didAutoCheck.current || !hasCezihIdentifier || isForeign) return
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
  }, [hasCezihIdentifier, isForeign, patientId, insuranceMutation, summary?.insurance?.last_checked, summary])

  const handleCheckInsurance = () => {
    if (!hasCezihIdentifier || isForeign) return
    insuranceMutation.mutate(patientId)
  }

  const handleDownloadPdf = (referenceId: string, contentUrl?: string, documentOid?: string) => {
    retrieveDoc.mutate({ id: referenceId, contentUrl, documentOid }, {
      onSuccess: (blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement("a")
        a.href = url
        a.download = `e-nalaz-${referenceId}.pdf`
        a.click()
        URL.revokeObjectURL(url)
      },
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

  const matchesCaseStatus = (clinicalStatus: string) => {
    if (casesStatusFilter === "all") return true
    if (casesStatusFilter === "active") return clinicalStatus !== "resolved"
    return clinicalStatus === casesStatusFilter
  }
  const matchesVisitStatus = (status: string) => {
    if (visitsStatusFilter === "all") return true
    if (visitsStatusFilter === "open") return status === "in-progress" || status === "planned"
    return status === visitsStatusFilter
  }
  const matchesFindingStatus = (storno: boolean) => {
    if (findingsStatusFilter === "all") return true
    if (findingsStatusFilter === "sent") return !storno
    return storno
  }

  const filteredCases = cases
    .filter((c) => matchesCaseStatus(c.clinical_status))
    .filter((c) => matchesIcdFilter(c.icd_code, icdFilter))
    .sort((a, b) => (b.onset_date ?? "").localeCompare(a.onset_date ?? ""))
  const filteredVisits = visits
    .filter((v) => matchesVisitStatus(v.status))
    .sort((a, b) => (b.period_start ?? "").localeCompare(a.period_start ?? ""))
  const filteredFindings = eNalazHistory
    .filter((n) => matchesFindingStatus(n.cezih_storno))
    .sort((a, b) => (b.datum ?? "").localeCompare(a.datum ?? ""))

  const pagedCases = filteredCases.slice(casesPage * PAGE_SIZE, (casesPage + 1) * PAGE_SIZE)
  const pagedVisits = filteredVisits.slice(visitsPage * PAGE_SIZE, (visitsPage + 1) * PAGE_SIZE)
  const pagedFindings = filteredFindings.slice(findingsPage * PAGE_SIZE, (findingsPage + 1) * PAGE_SIZE)

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
        {/* 1. Osiguranje (Croatian) / Strani državljanin (foreign) */}
        {isForeign ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <Globe className="h-4 w-4" />
              Strani državljanin
            </div>
            <div className="flex items-center gap-4 flex-wrap text-sm">
              {patient.broj_putovnice && (
                <span>
                  <span className="text-muted-foreground">Putovnica: </span>
                  <span className="font-mono">{patient.broj_putovnice}</span>
                </span>
              )}
              {patient.ehic_broj && (
                <span>
                  <span className="text-muted-foreground">EHIC: </span>
                  <span className="font-mono">{patient.ehic_broj}</span>
                </span>
              )}
              {patient.drzavljanstvo && (
                <span>
                  <span className="text-muted-foreground">Država: </span>
                  <span>{COUNTRY_HR[patient.drzavljanstvo] || patient.drzavljanstvo}</span>
                </span>
              )}
            </div>
          </div>
        ) : (
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
        )}

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

        {/* 3. Dijagnoze — status + ICD chapter filters, paginated */}
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <Stethoscope className="h-4 w-4" />
              Dijagnoze
              {cases.length > 0 && (
                <Badge variant="outline" className="text-xs ml-1">
                  {filteredCases.length}/{cases.length}
                </Badge>
              )}
            </div>
            {cases.length > 0 && (
              <div className="flex items-center gap-2">
                <Select value={casesStatusFilter} onValueChange={handleCasesStatusChange}>
                  <SelectTrigger className="h-7 w-[130px] text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CLINICAL_STATUS_FILTER_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value} className="text-xs">
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
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
              </div>
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
              {cases.length > 0 ? "Nema dijagnoza za odabrane filtere" : "Nema dijagnoza"}
            </p>
          ) : (
            <>
              <div className="space-y-1.5">
                {pagedCases.map((c) => (
                  <div key={c.case_id} className="flex items-center gap-2 flex-wrap">
                    <Badge className={CLINICAL_STATUS_COLORS[c.clinical_status] || "bg-gray-100 text-gray-600"}>
                      {CLINICAL_STATUS[c.clinical_status] || c.clinical_status || "Nema"}
                    </Badge>
                    <span className="font-mono text-sm">{c.icd_code}</span>
                    <span className="text-sm text-muted-foreground">{c.icd_display}</span>
                    {c.onset_date && (
                      <span className="text-xs text-muted-foreground">· od {formatDateHR(c.onset_date)}</span>
                    )}
                  </div>
                ))}
              </div>
              {filteredCases.length > PAGE_SIZE && (
                <TablePagination
                  page={casesPage}
                  pageSize={PAGE_SIZE}
                  total={filteredCases.length}
                  onPageChange={setCasesPage}
                />
              )}
            </>
          )}
        </div>

        <Separator />

        {/* 4. Posjete — status filter, paginated */}
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <Calendar className="h-4 w-4" />
              Posjete
              {visits.length > 0 && (
                <Badge variant="outline" className="text-xs ml-1">
                  {filteredVisits.length}/{visits.length}
                </Badge>
              )}
            </div>
            {visits.length > 0 && (
              <Select value={visitsStatusFilter} onValueChange={handleVisitsStatusChange}>
                <SelectTrigger className="h-7 w-[150px] text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {VISIT_STATUS_FILTER_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value} className="text-xs">
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
          {visitsQuery.isLoading ? (
            <div className="flex justify-center py-2">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : !hasCezihIdentifier ? (
            <p className="text-sm text-muted-foreground">Nema CEZIH identifikatora — dohvat nije moguć</p>
          ) : filteredVisits.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {visits.length > 0 ? "Nema posjeta za odabrani filter" : "Nema posjeta"}
            </p>
          ) : (
            <>
              <div className="space-y-1.5">
                {pagedVisits.map((v) => {
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
              {filteredVisits.length > PAGE_SIZE && (
                <TablePagination
                  page={visitsPage}
                  pageSize={PAGE_SIZE}
                  total={filteredVisits.length}
                  onPageChange={setVisitsPage}
                />
              )}
            </>
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
                  <div className="flex gap-0.5 shrink-0">
                    {d.content_url && !savedCezihRefIds.has(d.id) && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0"
                        onClick={() => importCezih.mutate({
                          patientId,
                          cezihReferenceId: d.id,
                          contentUrl: d.content_url!,
                          naziv: `CEZIH - ${d.svrha || d.id}`,
                        })}
                        disabled={importCezih.isPending}
                        title="Spremi u Dokumenti"
                      >
                        {importCezih.isPending ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <FolderDown className="h-3.5 w-3.5" />
                        )}
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0"
                      onClick={() => handleDownloadPdf(d.id, d.content_url)}
                      disabled={retrieveDoc.isPending}
                      title="Preuzmi PDF"
                    >
                      <Download className="h-3.5 w-3.5" />
                    </Button>
                  </div>
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

        {/* 7. Povijest e-Nalaza — status filter, paginated */}
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <FileText className="h-4 w-4" />
              Povijest e-Nalaza
              {eNalazHistory.length > 0 && (
                <Badge variant="outline" className="text-xs ml-1">
                  {filteredFindings.length}/{eNalazHistory.length}
                </Badge>
              )}
            </div>
            {eNalazHistory.length > 0 && (
              <Select value={findingsStatusFilter} onValueChange={handleFindingsStatusChange}>
                <SelectTrigger className="h-7 w-[130px] text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {E_NALAZ_FILTER_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value} className="text-xs">
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
          {filteredFindings.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {eNalazHistory.length > 0 ? "Nema e-Nalaza za odabrani filter" : "Nema poslanih e-Nalaza"}
            </p>
          ) : (
            <>
              <div className="space-y-1.5">
                {pagedFindings.map((n) => (
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
                        onClick={() => handleDownloadPdf(n.reference_id!, undefined, n.document_oid ?? undefined)}
                        disabled={retrieveDoc.isPending}
                        title="Preuzmi PDF"
                      >
                        <Download className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                ))}
              </div>
              {filteredFindings.length > PAGE_SIZE && (
                <TablePagination
                  page={findingsPage}
                  pageSize={PAGE_SIZE}
                  total={filteredFindings.length}
                  onPageChange={setFindingsPage}
                />
              )}
            </>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
