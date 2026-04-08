"use client"

import { useState, useEffect, useCallback } from "react"
import Link from "next/link"
import { Send, Loader2, Check, AlertTriangle } from "lucide-react"
import { toast } from "sonner"

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
import { PageHeader } from "@/components/shared/page-header"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { useCezihUnsentRecords } from "@/lib/hooks/use-medical-records"
import { useSendENalaz } from "@/lib/hooks/use-cezih"
import { usePermissions } from "@/lib/hooks/use-permissions"
import { useRecordTypeMaps } from "@/lib/hooks/use-record-types"
import { formatDateHR } from "@/lib/utils"

function CheckIcon({ checked }: { checked: boolean }) {
  return (
    <div className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors ${
      checked ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground/40"
    }`}>
      {checked && <Check className="h-3 w-3" />}
    </div>
  )
}

export default function CezihNalaziPage() {
  const { canPerformCezihOps } = usePermissions()
  const { data, isLoading, isError, error } = useCezihUnsentRecords()
  const sendENalaz = useSendENalaz()
  const { tipLabelMap, tipColorMap, isCezihMandatory } = useRecordTypeMaps()

  const allRecords = data?.items ?? []
  const records = allRecords.filter(
    (r) => isCezihMandatory.has(r.tip) && !r.cezih_sent
  )

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [sending, setSending] = useState(false)
  const [progress, setProgress] = useState({ current: 0, total: 0 })
  const [failedRecords, setFailedRecords] = useState<{ id: string; error: string }[]>([])

  // Pre-select all when records load
  useEffect(() => {
    setSelectedIds(new Set(records.map((r) => r.id)))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data])

  const toggleRecord = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (selectedIds.size === records.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(records.map((r) => r.id)))
    }
  }

  const handleSend = useCallback(async () => {
    const toSend = records.filter((r) => selectedIds.has(r.id))
    if (toSend.length === 0) return

    setSending(true)
    setProgress({ current: 0, total: toSend.length })
    setFailedRecords([])
    let successCount = 0
    const failed: { id: string; error: string }[] = []

    for (let i = 0; i < toSend.length; i++) {
      setProgress({ current: i + 1, total: toSend.length })
      try {
        await sendENalaz.mutateAsync({
          patient_id: toSend[i].patient_id,
          record_id: toSend[i].id,
        })
        successCount++
      } catch (err) {
        failed.push({
          id: toSend[i].id,
          error: err instanceof Error ? err.message : "Nepoznata greška",
        })
      }
    }

    setSending(false)
    setFailedRecords(failed)

    if (successCount > 0) {
      toast.success(`${successCount} nalaz${successCount === 1 ? "" : "a"} poslan${successCount === 1 ? "" : "o"} na CEZIH`)
    }
    if (failed.length > 0) {
      toast.error(
        `${failed.length} nalaz${failed.length === 1 ? "" : "a"} nije uspjelo poslati: ${failed.map((f) => f.error).join("; ")}`,
      )
    }
    setSelectedIds(new Set())
  }, [selectedIds, records, sendENalaz])

  if (!canPerformCezihOps) {
    return (
      <div className="space-y-6">
        <PageHeader title="CEZIH Nalazi" />
        <p className="text-sm text-muted-foreground">Nemate ovlasti za ovu stranicu.</p>
      </div>
    )
  }

  const allSelected = records.length > 0 && selectedIds.size === records.length

  return (
    <div className="space-y-6">
      <PageHeader title="CEZIH Nalazi" description="Neposlani obavezni nalazi za CEZIH — svi pacijenti" />

      {/* Failed records banner */}
      {failedRecords.length > 0 && !sending && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 space-y-1">
          <p className="text-sm font-medium text-destructive">
            {failedRecords.length} nalaz{failedRecords.length === 1 ? "" : "a"} nije uspjelo poslati:
          </p>
          {failedRecords.map((f) => {
            const record = records.find((r) => r.id === f.id)
            return (
              <p key={f.id} className="text-xs text-destructive/80">
                {record
                  ? `${record.patient_ime} ${record.patient_prezime} — ${tipLabelMap[record.tip] || record.tip} (${formatDateHR(record.datum)})`
                  : f.id}: {f.error}
              </p>
            )
          })}
        </div>
      )}

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
          <p className="text-muted-foreground">Nema neposlanih CEZIH nalaza</p>
          <p className="text-sm text-muted-foreground">Svi obavezni nalazi su poslani na CEZIH.</p>
        </div>
      ) : (
        <>
          {/* Action bar */}
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={toggleAll}
              className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <CheckIcon checked={allSelected} />
              <span>{allSelected ? "Odznači sve" : "Označi sve"} ({records.length})</span>
            </button>

            <div className="flex items-center gap-3">
              {sending && (
                <span className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Slanje {progress.current}/{progress.total}...
                </span>
              )}
              <Button
                onClick={handleSend}
                disabled={selectedIds.size === 0 || sending}
                className="bg-emerald-600 hover:bg-emerald-700 text-white"
              >
                {sending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Send className="mr-2 h-4 w-4" />
                )}
                {sending
                  ? `Slanje ${progress.current}/${progress.total}...`
                  : `Pošalji${selectedIds.size > 0 ? ` (${selectedIds.size})` : ""}`}
              </Button>
            </div>
          </div>

          {/* Table */}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10"></TableHead>
                <TableHead>Pacijent</TableHead>
                <TableHead>Datum</TableHead>
                <TableHead>Tip</TableHead>
                <TableHead className="hidden md:table-cell">Dijagnoza</TableHead>
                <TableHead className="hidden lg:table-cell">Doktor</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {records.map((r) => {
                const isFailed = failedRecords.some((f) => f.id === r.id)
                return (
                <TableRow
                  key={r.id}
                  className={`cursor-pointer ${isFailed ? "bg-destructive/5 border-l-2 border-l-destructive" : selectedIds.has(r.id) ? "bg-primary/5" : ""}`}
                  onClick={() => !sending && toggleRecord(r.id)}
                >
                  <TableCell>
                    <CheckIcon checked={selectedIds.has(r.id)} />
                  </TableCell>
                  <TableCell>
                    <Link
                      href={`/pacijenti/${r.patient_id}`}
                      className="font-medium hover:underline"
                      onClick={(e) => e.stopPropagation()}
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
                </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </>
      )}
    </div>
  )
}
