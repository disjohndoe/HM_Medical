"use client"

import { useState } from "react"
import Link from "next/link"
import { Send, AlertTriangle, Info } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { PageHeader } from "@/components/shared/page-header"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { TablePagination } from "@/components/shared/table-pagination"
import { NalazCezihGlossary } from "@/components/cezih/nalaz-cezih-glossary"
import { SendNalazDialog } from "@/components/cezih/send-nalaz-dialog"
import { useCezihUnsentRecords } from "@/lib/hooks/use-medical-records"
import { usePermissions } from "@/lib/hooks/use-permissions"
import { useRecordTypeMaps } from "@/lib/hooks/use-record-types"
import { formatDateHR } from "@/lib/utils"

const PAGE_SIZE = 20

export default function CezihNalaziPage() {
  const { canPerformCezihOps } = usePermissions()
  const [page, setPage] = useState(0)
  const { data, isLoading, isError, error } = useCezihUnsentRecords(page * PAGE_SIZE, PAGE_SIZE)
  const { tipLabelMap, tipColorMap, isCezihMandatory } = useRecordTypeMaps()

  const allRecords = data?.items ?? []
  const records = allRecords.filter(
    (r) => isCezihMandatory.has(r.tip) && !r.cezih_sent,
  )

  const [sendTarget, setSendTarget] = useState<{ patientId: string; patientMbo: string | null; recordId: string } | null>(null)

  if (!canPerformCezihOps) {
    return (
      <div className="space-y-6">
        <PageHeader title="Slanje e-Nalaza" />
        <p className="text-sm text-muted-foreground">Nemate ovlasti za ovu stranicu.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-2">
        <PageHeader
          title="Slanje e-Nalaza"
          description="Neposlani obavezni nalazi — svi pacijenti. Nakon uspješnog slanja postaju e-Nalazi na CEZIH-u."
        />
        <Popover>
          <PopoverTrigger
            aria-label="Objašnjenje Nalaz vs e-Nalaz"
            className="mt-1 text-muted-foreground hover:text-foreground"
          >
            <Info className="h-4 w-4" />
          </PopoverTrigger>
          <PopoverContent align="start" className="w-80">
            <NalazCezihGlossary />
          </PopoverContent>
        </Popover>
      </div>

      {isLoading ? (
        <LoadingSpinner text="Učitavanje..." />
      ) : isError ? (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
          <p className="text-sm text-destructive">
            Greška pri dohvatu neposlanih nalaza: {(error as Error)?.message ?? "Nepoznata greška"}
          </p>
        </div>
      ) : records.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed py-16">
          <AlertTriangle className="h-8 w-8 text-muted-foreground" />
          <p className="text-muted-foreground">Nema e-Nalaza za slanje</p>
          <p className="text-sm text-muted-foreground">Svi obavezni nalazi su poslani na CEZIH.</p>
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
                <TableHead className="w-32 text-right">Akcija</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {records.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    <Link
                      href={`/pacijenti/${r.patient_id}`}
                      className="font-medium hover:underline"
                    >
                      {r.patient_ime && r.patient_prezime
                        ? `${r.patient_ime} ${r.patient_prezime}`
                        : "—"}
                    </Link>
                  </TableCell>
                  <TableCell>{formatDateHR(r.datum)}</TableCell>
                  <TableCell>
                    <Badge
                      variant="secondary"
                      className={`text-xs ${tipColorMap[r.tip] || ""}`}
                    >
                      {tipLabelMap[r.tip] || r.tip}
                    </Badge>
                  </TableCell>
                  <TableCell className="hidden md:table-cell">
                    {r.dijagnoza_tekst
                      ? `${r.dijagnoza_mkb ? `${r.dijagnoza_mkb} — ` : ""}${r.dijagnoza_tekst}`
                      : r.dijagnoza_mkb || "—"}
                  </TableCell>
                  <TableCell className="hidden lg:table-cell">
                    {r.doktor_prezime
                      ? `${r.doktor_ime} ${r.doktor_prezime}`
                      : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      size="sm"
                      className="bg-emerald-600 hover:bg-emerald-700 text-white"
                      disabled={!r.patient_mbo}
                      title={!r.patient_mbo ? "Pacijent nema MBO — potreban za CEZIH" : undefined}
                      onClick={() =>
                        setSendTarget({
                          patientId: r.patient_id,
                          patientMbo: r.patient_mbo,
                          recordId: r.id,
                        })
                      }
                    >
                      <Send className="mr-2 h-4 w-4" />
                      Pošalji
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {data && data.total > 0 && (
            <TablePagination
              page={page}
              pageSize={PAGE_SIZE}
              total={data.total}
              onPageChange={setPage}
            />
          )}
        </>
      )}

      {sendTarget && (
        <SendNalazDialog
          open={!!sendTarget}
          onOpenChange={(open) => !open && setSendTarget(null)}
          patientId={sendTarget.patientId}
          patientMbo={sendTarget.patientMbo}
          onlyRecordId={sendTarget.recordId}
        />
      )}
    </div>
  )
}
