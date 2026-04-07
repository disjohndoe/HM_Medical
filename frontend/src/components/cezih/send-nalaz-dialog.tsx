"use client"

import { useState, useEffect, useCallback } from "react"
import { Send, Loader2, AlertTriangle, Check } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

function CheckIcon({ checked }: { checked: boolean }) {
  return (
    <div className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors ${
      checked ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground/40"
    }`}>
      {checked && <Check className="h-3 w-3" />}
    </div>
  )
}
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { MockBadge } from "@/components/cezih/mock-badge"
import { useMedicalRecords } from "@/lib/hooks/use-medical-records"
import { useSendENalaz } from "@/lib/hooks/use-cezih"
import { useRecordTypeMaps } from "@/lib/hooks/use-record-types"
import { formatDateHR } from "@/lib/utils"

interface SendNalazDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  patientId: string
  patientMbo?: string | null
}

export function SendNalazDialog({ open, onOpenChange, patientId, patientMbo }: SendNalazDialogProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [sending, setSending] = useState(false)
  const [progress, setProgress] = useState({ current: 0, total: 0 })
  const [failedRecords, setFailedRecords] = useState<{ id: string; error: string }[]>([])

  const { data } = useMedicalRecords(patientId)
  const sendENalaz = useSendENalaz()
  const { tipLabelMap, tipColorMap, isCezihMandatory } = useRecordTypeMaps()

  const records = data?.items ?? []
  const eligibleRecords = records.filter(
    (r) => isCezihMandatory.has(r.tip) && !r.cezih_sent
  )

  // Pre-select all eligible records when dialog opens or records change
  useEffect(() => {
    if (open) {
      setSelectedIds(new Set(eligibleRecords.map((r) => r.id)))
      setProgress({ current: 0, total: 0 })
      setFailedRecords([])
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const toggleRecord = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (selectedIds.size === eligibleRecords.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(eligibleRecords.map((r) => r.id)))
    }
  }

  const handleSend = useCallback(async () => {
    const ids = Array.from(selectedIds)
    if (ids.length === 0) return

    setSending(true)
    setProgress({ current: 0, total: ids.length })
    setFailedRecords([])
    let successCount = 0
    const failed: { id: string; error: string }[] = []

    for (let i = 0; i < ids.length; i++) {
      setProgress({ current: i + 1, total: ids.length })
      try {
        await sendENalaz.mutateAsync({
          patient_id: patientId,
          record_id: ids[i],
        })
        successCount++
      } catch (err) {
        failed.push({
          id: ids[i],
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

    if (failed.length === 0) {
      setSelectedIds(new Set())
      onOpenChange(false)
    }
    // Keep dialog open on partial failure so user can see which records failed
  }, [selectedIds, patientId, sendENalaz, onOpenChange])

  const allSelected = eligibleRecords.length > 0 && selectedIds.size === eligibleRecords.length

  return (
    <Dialog open={open} onOpenChange={sending ? undefined : onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <DialogTitle>Pošalji nalaze na CEZIH</DialogTitle>
            <MockBadge />
          </div>
          <DialogDescription>
            Odaberite nalaze za slanje na CEZIH
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          {eligibleRecords.length === 0 ? (
            <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-8">
              <AlertTriangle className="h-5 w-5 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                Nema neposlanih nalaza za CEZIH
              </p>
            </div>
          ) : (
            <>
              {/* Select all toggle */}
              <button
                type="button"
                onClick={toggleAll}
                className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                <CheckIcon checked={allSelected} />
                <span>{allSelected ? "Odznači sve" : "Označi sve"}</span>
              </button>

              <div className="space-y-1.5 max-h-[300px] overflow-y-auto">
                {eligibleRecords.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => toggleRecord(r.id)}
                    disabled={sending}
                    className={`w-full text-left rounded-lg border px-3 py-2.5 transition-colors ${
                      selectedIds.has(r.id)
                        ? "border-primary bg-primary/5"
                        : "border-border hover:bg-muted/50"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <CheckIcon checked={selectedIds.has(r.id)} />
                      <Badge
                        variant="secondary"
                        className={`text-xs ${tipColorMap[r.tip] || ""}`}
                      >
                        {tipLabelMap[r.tip] || r.tip}
                      </Badge>
                      <span className="ml-auto text-xs text-muted-foreground">
                        {formatDateHR(r.datum)}
                      </span>
                    </div>
                    {r.dijagnoza_tekst && (
                      <p className="mt-1 ml-6 text-xs text-muted-foreground truncate">
                        {r.dijagnoza_mkb && <span className="font-mono mr-1">{r.dijagnoza_mkb}</span>}
                        {r.dijagnoza_tekst}
                      </p>
                    )}
                  </button>
                ))}
              </div>
            </>
          )}

          {/* Progress indicator */}
          {sending && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Slanje {progress.current}/{progress.total}...</span>
            </div>
          )}

          {/* Failed records */}
          {failedRecords.length > 0 && !sending && (
            <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 space-y-1">
              <p className="text-sm font-medium text-destructive">
                {failedRecords.length} nalaz{failedRecords.length === 1 ? "" : "a"} nije uspjelo poslati:
              </p>
              {failedRecords.map((f) => {
                const record = eligibleRecords.find((r) => r.id === f.id)
                return (
                  <p key={f.id} className="text-xs text-destructive/80">
                    {record ? `${tipLabelMap[record.tip] || record.tip} (${formatDateHR(record.datum)})` : f.id}: {f.error}
                  </p>
                )
              })}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            onClick={handleSend}
            disabled={selectedIds.size === 0 || sending || !patientMbo}
            title={!patientMbo ? "Pacijent nema MBO — potreban za CEZIH" : undefined}
          >
            {sending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Send className="mr-2 h-4 w-4" />
            )}
            {!patientMbo
              ? "MBO nije dostupan"
              : sending
                ? `Slanje ${progress.current}/${progress.total}...`
                : `Pošalji${selectedIds.size > 0 ? ` (${selectedIds.size})` : ""}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
