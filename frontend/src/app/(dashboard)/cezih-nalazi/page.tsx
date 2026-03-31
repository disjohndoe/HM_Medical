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
import { MockBadge } from "@/components/cezih/mock-badge"
import { useCezihUnsentRecords } from "@/lib/hooks/use-medical-records"
import { useSendENalaz } from "@/lib/hooks/use-cezih"
import { usePermissions } from "@/lib/hooks/use-permissions"
import {
  CEZIH_MANDATORY_TYPES,
  RECORD_TIP,
  RECORD_TIP_COLORS,
} from "@/lib/constants"
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
  const { data, isLoading } = useCezihUnsentRecords()
  const sendENalaz = useSendENalaz()

  const allRecords = data?.items ?? []
  const records = allRecords.filter(
    (r) => CEZIH_MANDATORY_TYPES.has(r.tip) && !r.cezih_sent
  )

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [sending, setSending] = useState(false)
  const [progress, setProgress] = useState({ current: 0, total: 0 })

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
    let successCount = 0

    for (let i = 0; i < toSend.length; i++) {
      setProgress({ current: i + 1, total: toSend.length })
      try {
        await sendENalaz.mutateAsync({
          patient_id: toSend[i].patient_id,
          record_id: toSend[i].id,
        })
        successCount++
      } catch {
        // continue sending remaining
      }
    }

    setSending(false)
    if (successCount > 0) {
      toast.success(`${successCount} nalaz${successCount === 1 ? "" : "a"} poslan${successCount === 1 ? "" : "o"} na CEZIH`)
    }
    if (successCount < toSend.length) {
      toast.error(`${toSend.length - successCount} nalaz${toSend.length - successCount === 1 ? "" : "a"} nije uspjelo poslati`)
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
      <PageHeader title="CEZIH Nalazi" description="Neposlani obavezni nalazi za CEZIH — svi pacijenti">
        <MockBadge />
      </PageHeader>

      {isLoading ? (
        <LoadingSpinner text="Učitavanje..." />
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
              {records.map((r) => (
                <TableRow
                  key={r.id}
                  className={`cursor-pointer ${selectedIds.has(r.id) ? "bg-primary/5" : ""}`}
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
                      className={`text-xs ${RECORD_TIP_COLORS[r.tip] || ""}`}
                    >
                      {RECORD_TIP[r.tip] || r.tip}
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
              ))}
            </TableBody>
          </Table>
        </>
      )}
    </div>
  )
}
