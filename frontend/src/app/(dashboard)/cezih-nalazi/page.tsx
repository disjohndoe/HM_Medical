"use client"

import { useState } from "react"
import Link from "next/link"
import { Send, AlertTriangle, Info, Trash2 } from "lucide-react"

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
import { SortableTableHead } from "@/components/ui/sortable-table-head"
import { useTableSort } from "@/lib/hooks/use-table-sort"
import { PageHeader } from "@/components/shared/page-header"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { TablePagination } from "@/components/shared/table-pagination"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { NalazCezihGlossary } from "@/components/cezih/nalaz-cezih-glossary"
import { SendNalazDialog } from "@/components/cezih/send-nalaz-dialog"
import { CezihStatusBadge } from "@/components/cezih/cezih-status-badge"
import { useCezihUnsentRecords, useDeleteMedicalRecord } from "@/lib/hooks/use-medical-records"
import { usePermissions } from "@/lib/hooks/use-permissions"
import { useRecordTypeMaps } from "@/lib/hooks/use-record-types"
import { formatDateHR } from "@/lib/utils"
import { toast } from "sonner"
import type { MedicalRecord } from "@/lib/types"

const PAGE_SIZE = 20

export default function CezihNalaziPage() {
  const { canPerformCezihOps } = usePermissions()
  const [page, setPage] = useState(0)
  const { data, isLoading, isError, error } = useCezihUnsentRecords(page * PAGE_SIZE, PAGE_SIZE)
  const { tipLabelMap, tipColorMap, isCezihEligible } = useRecordTypeMaps()

  const allRecords = data?.items ?? []
  const records = allRecords.filter(
    (r) => isCezihEligible.has(r.tip) && !r.cezih_sent,
  )

  const [sendTarget, setSendTarget] = useState<{ patientId: string; hasCezihIdentifier: boolean; recordId: string } | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<MedicalRecord | null>(null)
  const deleteRecord = useDeleteMedicalRecord()

  async function confirmDelete() {
    if (!deleteTarget) return
    try {
      await deleteRecord.mutateAsync(deleteTarget.id)
      toast.success("Nalaz obrisan")
      setDeleteTarget(null)
    } catch {
      // useDeleteMedicalRecord already surfaces an error toast
    }
  }

  const { sorted, sortKey, sortDir, toggleSort } = useTableSort(records, {
    defaultKey: "datum",
    defaultDir: "desc",
    keyAccessors: {
      pacijent: (r) => `${r.patient_prezime ?? ""} ${r.patient_ime ?? ""}`.trim(),
      tip: (r) => tipLabelMap[r.tip] || r.tip,
      dijagnoza: (r) => r.dijagnoza_tekst || r.dijagnoza_mkb || "",
      doktor: (r) => `${r.doktor_prezime ?? ""} ${r.doktor_ime ?? ""}`.trim(),
    },
  })

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
                <SortableTableHead columnKey="pacijent" label="Pacijent" currentKey={sortKey} currentDir={sortDir} onSort={toggleSort} />
                <SortableTableHead columnKey="datum" label="Datum" currentKey={sortKey} currentDir={sortDir} onSort={toggleSort} />
                <SortableTableHead columnKey="tip" label="Tip" currentKey={sortKey} currentDir={sortDir} onSort={toggleSort} />
                <SortableTableHead columnKey="dijagnoza" label="Dijagnoza" currentKey={sortKey} currentDir={sortDir} onSort={toggleSort} className="hidden md:table-cell" />
                <SortableTableHead columnKey="doktor" label="Doktor" currentKey={sortKey} currentDir={sortDir} onSort={toggleSort} className="hidden lg:table-cell" />
                <TableHead>Status</TableHead>
                <TableHead className="w-44 text-right">Akcija</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((r) => (
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
                  <TableCell>
                    {r.cezih_last_error_code ? (
                      <CezihStatusBadge record={r} />
                    ) : (
                      <span className="text-xs text-muted-foreground">Nije pokušano</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      <Button
                        size="sm"
                        className="bg-emerald-600 hover:bg-emerald-700 text-white"
                        disabled={!r.patient_has_cezih_identifier}
                        title={
                          !r.patient_has_cezih_identifier
                            ? "Pacijent nema CEZIH identifikator (potreban za CEZIH)"
                            : r.cezih_last_error_code
                              ? "Pokušaj ponovno poslati na CEZIH"
                              : undefined
                        }
                        onClick={() =>
                          setSendTarget({
                            patientId: r.patient_id,
                            hasCezihIdentifier: !!r.patient_has_cezih_identifier,
                            recordId: r.id,
                          })
                        }
                      >
                        <Send className="mr-2 h-4 w-4" />
                        Pošalji
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-destructive hover:text-destructive"
                        title="Trajno obriši nalaz lokalno (ne šalje se ništa na CEZIH)"
                        onClick={() => setDeleteTarget(r)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
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
          hasCezihIdentifier={sendTarget.hasCezihIdentifier}
          onlyRecordId={sendTarget.recordId}
        />
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Brisanje nalaza"
        description={
          <>
            <span className="block">
              Spremate se obrisati nalaz: &quot;{deleteTarget ? tipLabelMap[deleteTarget.tip] || deleteTarget.tip : ""}&quot;
            </span>
            <span className="mt-1 block">Obrišite ovaj nalaz?</span>
          </>
        }
        warning="Ova akcija se ne može poništiti!"
        confirmLabel="Obriši"
        variant="destructive"
        onConfirm={confirmDelete}
        loading={deleteRecord.isPending}
      />
    </div>
  )
}
