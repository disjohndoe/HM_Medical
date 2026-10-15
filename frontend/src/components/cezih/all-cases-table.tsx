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
import { useAllCases } from "@/lib/hooks/use-cezih"
import { CLINICAL_STATUS, CLINICAL_STATUS_COLORS, VERIFICATION_STATUS } from "@/lib/constants"
import { formatDateHR } from "@/lib/utils"

const PAGE_SIZE = 20

/** Read-only tenant-wide Slučajevi listing for the global /cezih tab.
 *
 * Lists the local CEZIH case mirror across all patients; creating cases and
 * changing clinical status stays on the patient's CEZIH tab (follow the
 * Pacijent link in any row).
 */
export function AllCasesTable() {
  const [page, setPage] = useState(0)
  const { data, isLoading, isError, error } = useAllCases(page * PAGE_SIZE, PAGE_SIZE)

  const cases = data?.items ?? []

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          Slučajevi — svi pacijenti
          {data && (
            <span className="text-xs font-normal text-muted-foreground">({data.total} ukupno)</span>
          )}
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          Pregled svih slučajeva iz lokalnog CEZIH ogledala. Kreiranje i promjene statusa dostupni
          su na kartici pacijenta — kliknite ime pacijenta.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <LoadingSpinner text="Učitavanje..." />
        ) : isError ? (
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
            <p className="text-sm text-destructive">
              Greška pri dohvatu slučajeva: {(error as Error)?.message ?? "Nepoznata greška"}
            </p>
          </div>
        ) : cases.length === 0 ? (
          <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-12">
            <p className="text-muted-foreground">Nema slučajeva</p>
            <p className="text-sm text-muted-foreground">
              Slučajevi se pojavljuju nakon prvog otvaranja pacijentove CEZIH kartice ili kreiranja
              slučaja.
            </p>
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Pacijent</TableHead>
                  <TableHead className="w-[110px]">Status</TableHead>
                  <TableHead className="hidden md:table-cell">Verifikacija</TableHead>
                  <TableHead className="w-[110px]">MKB šifra</TableHead>
                  <TableHead className="hidden lg:table-cell">Naziv</TableHead>
                  <TableHead>Početak</TableHead>
                  <TableHead className="hidden md:table-cell">Izmjena</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cases.map((c) => (
                  <TableRow key={c.case_id}>
                    <TableCell>
                      {c.patient_id ? (
                        <Link
                          href={`/pacijenti/${c.patient_id}?tab=cezih`}
                          className="font-medium hover:underline"
                        >
                          {c.patient_ime && c.patient_prezime
                            ? `${c.patient_ime} ${c.patient_prezime}`
                            : "—"}
                        </Link>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge className={CLINICAL_STATUS_COLORS[c.clinical_status] || "bg-gray-100"}>
                        {CLINICAL_STATUS[c.clinical_status] || c.clinical_status}
                      </Badge>
                    </TableCell>
                    <TableCell className="hidden text-xs text-muted-foreground md:table-cell">
                      {VERIFICATION_STATUS[c.verification_status || ""] ||
                        c.verification_status ||
                        "—"}
                    </TableCell>
                    <TableCell className="font-mono text-sm font-medium">{c.icd_code}</TableCell>
                    <TableCell className="hidden text-sm text-muted-foreground lg:table-cell">
                      {c.icd_display}
                      {c.note && (
                        <span className="ml-1 text-xs text-blue-600" title={c.note}>
                          [bilješka]
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">{formatDateHR(c.onset_date)}</TableCell>
                    <TableCell className="hidden text-sm text-muted-foreground md:table-cell">
                      {c.updated_at ? formatDateHR(c.updated_at) : "—"}
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
