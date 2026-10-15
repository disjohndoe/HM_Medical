"use client"

import { useState } from "react"
import Link from "next/link"
import { Building2, ExternalLink } from "lucide-react"

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
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { TablePagination } from "@/components/shared/table-pagination"
import { useAllVisits } from "@/lib/hooks/use-cezih"
import { formatDateTimeHR } from "@/lib/utils"

const PAGE_SIZE = 20

// Same wording/colors as the per-patient Posjete table (visit-management.tsx)
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

/** Read-only tenant-wide Posjete listing for the global /cezih tab.

 * Lists the local CEZIH visit mirror across all patients; creating visits
 * and running actions stays on the patient's CEZIH tab (follow the Pacijent
 * link in any row).
 */
export function AllVisitsTable() {
  const [page, setPage] = useState(0)
  const { data, isLoading, isError, error } = useAllVisits(page * PAGE_SIZE, PAGE_SIZE)

  const visits = data?.items ?? []

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          Posjete — svi pacijenti
          {data && (
            <span className="text-xs font-normal text-muted-foreground">({data.total} ukupno)</span>
          )}
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Pregled svih posjeta iz lokalnog CEZIH ogledala. Kreiranje i akcije (zatvaranje, storno)
          dostupni su na kartici pacijenta — kliknite ime pacijenta.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <LoadingSpinner text="Učitavanje..." />
        ) : isError ? (
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
            <p className="text-sm text-destructive">
              Greška pri dohvatu posjeta: {(error as Error)?.message ?? "Nepoznata greška"}
            </p>
          </div>
        ) : visits.length === 0 ? (
          <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-12">
            <p className="text-muted-foreground">Nema posjeta</p>
            <p className="text-sm text-muted-foreground">
              Posjete se pojavljuju nakon prvog otvaranja pacijentove CEZIH kartice ili kreiranja posjete.
            </p>
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[100px]">Izvor</TableHead>
                  <TableHead>Pacijent</TableHead>
                  <TableHead className="w-[110px]">Status</TableHead>
                  <TableHead className="hidden md:table-cell">Način prijema</TableHead>
                  <TableHead className="hidden lg:table-cell">Tip posjete</TableHead>
                  <TableHead className="hidden xl:table-cell">Razlog</TableHead>
                  <TableHead>Početak</TableHead>
                  <TableHead className="hidden md:table-cell">Kraj</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visits.map((v) => {
                  const external = v.is_ours === false
                  return (
                    <TableRow key={v.visit_id} className={external ? "bg-muted/30" : ""}>
                      <TableCell>
                        {external ? (
                          <Badge variant="outline" className="text-xs gap-1 text-muted-foreground">
                            <ExternalLink className="h-3 w-3" />
                            Vanjska
                          </Badge>
                        ) : (
                          <Badge variant="default" className="bg-primary/90 text-xs gap-1">
                            <Building2 className="h-3 w-3" />
                            Naša
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        {v.patient_id ? (
                          <Link
                            href={`/pacijenti/${v.patient_id}?tab=cezih`}
                            className="font-medium hover:underline"
                          >
                            {v.patient_ime && v.patient_prezime
                              ? `${v.patient_ime} ${v.patient_prezime}`
                              : "—"}
                          </Link>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary" className={VISIT_STATUS_COLORS[v.status] || ""}>
                          {VISIT_STATUS_LABELS[v.status] || v.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="hidden text-sm md:table-cell">
                        {v.visit_type_display || v.visit_type || "—"}
                      </TableCell>
                      <TableCell className="hidden text-sm lg:table-cell">
                        {v.tip_posjete_display || v.tip_posjete || "—"}
                      </TableCell>
                      <TableCell className="hidden text-sm text-muted-foreground xl:table-cell">
                        {v.reason || "—"}
                      </TableCell>
                      <TableCell className="text-sm">
                        {v.period_start ? formatDateTimeHR(v.period_start) : "—"}
                      </TableCell>
                      <TableCell className="hidden text-sm md:table-cell">
                        {v.period_end ? formatDateTimeHR(v.period_end) : "—"}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
            {data && data.total > PAGE_SIZE && (
              <TablePagination
                page={page}
                pageSize={PAGE_SIZE}
                total={data.total}
                onPageChange={setPage}
              />
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
