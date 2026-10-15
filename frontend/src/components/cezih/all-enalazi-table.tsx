"use client"

import { useState } from "react"
import Link from "next/link"

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
import { CezihStatusBadge } from "@/components/cezih/cezih-status-badge"
import { useCezihSentRecords } from "@/lib/hooks/use-medical-records"
import { useRecordTypeMaps } from "@/lib/hooks/use-record-types"
import { formatDateHR, formatDateTimeHR } from "@/lib/utils"

const PAGE_SIZE = 20

/** Read-only tenant-wide e-Nalazi history for the global /cezih tab.
 *
 * The complement of the Slanje e-Nalaza page (the unsent queue): everything
 * already sent to CEZIH, with its lifecycle status (poslan / storniran /
 * greška). Opening a nalaz stays on the patient — follow the Pacijent link.
 */
export function AllEnalaziTable() {
  const [page, setPage] = useState(0)
  const { data, isLoading, isError, error } = useCezihSentRecords(page * PAGE_SIZE, PAGE_SIZE)
  const { tipLabelMap, tipColorMap } = useRecordTypeMaps()

  const records = data?.items ?? []

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          e-Nalazi — svi pacijenti
          {data && (
            <span className="text-xs font-normal text-muted-foreground">({data.total} ukupno)</span>
          )}
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Povijest nalaza poslanih na CEZIH. Neposlani nalazi nalaze se na stranici Slanje e-Nalaza
          u izborniku.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <LoadingSpinner text="Učitavanje..." />
        ) : isError ? (
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
            <p className="text-sm text-destructive">
              Greška pri dohvatu e-Nalaza: {(error as Error)?.message ?? "Nepoznata greška"}
            </p>
          </div>
        ) : records.length === 0 ? (
          <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-12">
            <p className="text-muted-foreground">Nema poslanih e-Nalaza</p>
            <p className="text-sm text-muted-foreground">
              Nakon slanja nalaza na CEZIH pojavljuje se ovdje.
            </p>
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Pacijent</TableHead>
                  <TableHead>Datum</TableHead>
                  <TableHead>Tip</TableHead>
                  <TableHead className="hidden md:table-cell">Dijagnoza</TableHead>
                  <TableHead className="hidden lg:table-cell">Doktor</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="hidden md:table-cell">Poslano</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {records.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell>
                      <Link
                        href={`/pacijenti/${r.patient_id}?tab=cezih`}
                        className="font-medium hover:underline"
                      >
                        {r.patient_ime && r.patient_prezime
                          ? `${r.patient_ime} ${r.patient_prezime}`
                          : "—"}
                      </Link>
                    </TableCell>
                    <TableCell className="text-sm">{formatDateHR(r.datum)}</TableCell>
                    <TableCell>
                      <Badge
                        variant="secondary"
                        className={`text-xs ${tipColorMap[r.tip] || ""}`}
                      >
                        {tipLabelMap[r.tip] || r.tip}
                      </Badge>
                    </TableCell>
                    <TableCell className="hidden text-sm text-muted-foreground md:table-cell">
                      {r.dijagnoza_tekst
                        ? `${r.dijagnoza_mkb ? `${r.dijagnoza_mkb} — ` : ""}${r.dijagnoza_tekst}`
                        : r.dijagnoza_mkb || "—"}
                    </TableCell>
                    <TableCell className="hidden text-sm text-muted-foreground lg:table-cell">
                      {r.doktor_prezime ? `${r.doktor_ime ?? ""} ${r.doktor_prezime}` : "—"}
                    </TableCell>
                    <TableCell>
                      <CezihStatusBadge record={r} />
                    </TableCell>
                    <TableCell className="hidden text-sm text-muted-foreground md:table-cell">
                      {r.cezih_sent_at ? formatDateTimeHR(r.cezih_sent_at) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
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
