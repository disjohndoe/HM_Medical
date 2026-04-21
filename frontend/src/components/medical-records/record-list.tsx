"use client"

import { useState, useRef, useEffect } from "react"
import { PlusIcon, PencilIcon, Send, Info, Download, Loader2 } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { api } from "@/lib/api-client"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
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
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { TablePagination } from "@/components/shared/table-pagination"
import { RecordForm } from "./record-form"
import { CezihStatusBadge } from "@/components/cezih/cezih-status-badge"
import { SendNalazDialog } from "@/components/cezih/send-nalaz-dialog"
import { NalazCezihGlossary } from "@/components/cezih/nalaz-cezih-glossary"
import { useMedicalRecords } from "@/lib/hooks/use-medical-records"
import { useRecordTypeMaps } from "@/lib/hooks/use-record-types"
import { usePermissions } from "@/lib/hooks/use-permissions"
import { RECORD_SENSITIVITY, RECORD_SENSITIVITY_COLORS } from "@/lib/constants"
import { formatDateHR } from "@/lib/utils"
import type { MedicalRecord } from "@/lib/types"

const PAGE_SIZE = 30

interface RecordListProps {
  patientId: string
  hasCezihIdentifier?: boolean
  highlightRecordId?: string | null
  onHighlightConsumed?: () => void
}

export function RecordList({ patientId, hasCezihIdentifier = false, highlightRecordId, onHighlightConsumed }: RecordListProps) {
  const [tipFilter, setTipFilter] = useState<string>("")
  const [page, setPage] = useState(0)
  const [formOpen, setFormOpen] = useState(false)
  const [editRecord, setEditRecord] = useState<MedicalRecord | null>(null)
  const [sendNalazOpen, setSendNalazOpen] = useState(false)
  const [sendRecordId, setSendRecordId] = useState<string | undefined>()
  const [downloadingId, setDownloadingId] = useState<string | null>(null)
  const downloadingRef = useRef<Set<string>>(new Set())

  const handleDownloadPdf = async (record: MedicalRecord) => {
    if (downloadingRef.current.has(record.id)) return
    downloadingRef.current.add(record.id)
    setDownloadingId(record.id)
    try {
      const res = await api.fetchRaw(`/medical-records/${record.id}/pdf`)
      const blob = await res.blob()
      const disposition = res.headers.get("content-disposition") || ""
      const match = disposition.match(/filename="?([^"]+)"?/)
      const filename = match ? match[1] : `nalaz_${record.datum}_${record.id.slice(0, 4)}.pdf`
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
      const digitallySigned = res.headers.get("x-pdf-digitally-signed") === "true"
      if (digitallySigned) {
        toast.success("PDF preuzet i digitalno potpisan.")
      } else {
        toast.warning("PDF preuzet bez digitalnog potpisa.")
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Greška pri preuzimanju PDF-a")
    } finally {
      downloadingRef.current.delete(record.id)
      setDownloadingId(null)
    }
  }

  const { canCreateMedicalRecord, canEditMedicalRecord } = usePermissions()
  const { recordTypes, tipLabelMap, tipColorMap, isCezihEligible } = useRecordTypeMaps()
  const cezihRecordTypes = recordTypes.filter((rt) => isCezihEligible.has(rt.slug))
  const { data, isLoading } = useMedicalRecords(
    patientId,
    tipFilter || undefined,
    undefined,
    undefined,
    page * PAGE_SIZE,
    PAGE_SIZE,
  )
  const records = (data?.items ?? []).filter((r) => isCezihEligible.has(r.tip))

  useEffect(() => {
    if (!highlightRecordId) return
    const match = records.find((r) => r.id === highlightRecordId)
    if (match) {
      setEditRecord(match)
      onHighlightConsumed?.()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlightRecordId, records.length])

  const { sorted, sortKey, sortDir, toggleSort } = useTableSort(records, {
    defaultKey: "datum",
    defaultDir: "desc",
    keyAccessors: {
      tip: (r: MedicalRecord) => tipLabelMap[r.tip] || r.tip,
      dijagnoza: (r: MedicalRecord) => r.dijagnoza_tekst || r.dijagnoza_mkb || "",
      doktor: (r: MedicalRecord) => `${r.doktor_prezime ?? ""} ${r.doktor_ime ?? ""}`.trim(),
      status: (r: MedicalRecord) => (r.cezih_sent ? 1 : 0),
    },
  })

  if (isLoading) {
    return <LoadingSpinner text="Učitavanje..." />
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Select value={tipFilter} onValueChange={(v) => { setTipFilter(v ?? ""); setPage(0) }}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Svi tipovi">
              {tipFilter ? recordTypes.find((rt) => rt.slug === tipFilter)?.label : undefined}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {cezihRecordTypes.map((rt) => (
              <SelectItem key={rt.slug} value={rt.slug}>
                {rt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {canCreateMedicalRecord && (
          <Button onClick={() => setFormOpen(true)}>
            <PlusIcon className="mr-2 h-4 w-4" />
            Novi nalaz
          </Button>
        )}
      </div>

      {records.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-12">
          <p className="text-muted-foreground">Nema nalaza</p>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <SortableTableHead columnKey="datum" label="Datum" currentKey={sortKey} currentDir={sortDir} onSort={toggleSort} />
              <SortableTableHead columnKey="tip" label="Tip" currentKey={sortKey} currentDir={sortDir} onSort={toggleSort} />
              <SortableTableHead columnKey="dijagnoza" label="Dijagnoza" currentKey={sortKey} currentDir={sortDir} onSort={toggleSort} className="hidden md:table-cell" />
              <SortableTableHead columnKey="doktor" label="Doktor" currentKey={sortKey} currentDir={sortDir} onSort={toggleSort} className="hidden lg:table-cell" />
              <TableHead
                role="button"
                tabIndex={0}
                onClick={() => toggleSort("status")}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault()
                    toggleSort("status")
                  }
                }}
                className="cursor-pointer select-none hover:bg-muted/50"
              >
                <div className="flex items-center gap-1">
                  <span>Status e-Nalaza</span>
                  <Popover>
                    <PopoverTrigger
                      aria-label="Objašnjenje statusa e-Nalaza"
                      className="text-muted-foreground hover:text-foreground"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Info className="h-3.5 w-3.5" />
                    </PopoverTrigger>
                    <PopoverContent align="start" className="w-80">
                      <NalazCezihGlossary />
                    </PopoverContent>
                  </Popover>
                </div>
              </TableHead>
              <TableHead className="text-right">Akcije</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((r) => (
              <TableRow key={r.id}>
                <TableCell>{formatDateHR(r.datum)}</TableCell>
                <TableCell>
                  <Badge
                    variant="secondary"
                    className={tipColorMap[r.tip] || ""}
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
                  <div className="flex flex-wrap items-center gap-1">
                    {r.sensitivity && r.sensitivity !== "standard" && (
                      <Badge
                        variant="secondary"
                        className={`${RECORD_SENSITIVITY_COLORS[r.sensitivity] || ""} hidden sm:inline-flex`}
                      >
                        {RECORD_SENSITIVITY[r.sensitivity]}
                      </Badge>
                    )}
                    <CezihStatusBadge
                      record={r}
                      showIcon
                      size="sm"
                      labelClassName="hidden sm:inline"
                    />
                  </div>
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => handleDownloadPdf(r)}
                      disabled={downloadingId === r.id}
                      title="Preuzmi PDF"
                    >
                      {downloadingId === r.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Download className="h-4 w-4" />
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => {
                        setSendRecordId(r.id)
                        setSendNalazOpen(true)
                      }}
                      disabled={!!r.cezih_sent}
                      title={r.cezih_sent ? "Već poslano na CEZIH" : "Pošalji e-Nalaz"}
                    >
                      <Send className="h-4 w-4" />
                    </Button>
                    {canEditMedicalRecord && (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => setEditRecord(r)}
                        title="Uredi"
                      >
                        <PencilIcon className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {data && data.total > 0 && (
        <TablePagination
          page={page}
          pageSize={PAGE_SIZE}
          total={data.total}
          onPageChange={setPage}
        />
      )}

      <RecordForm
        open={formOpen}
        onOpenChange={setFormOpen}
        patientId={patientId}
      />

      <RecordForm
        open={!!editRecord}
        onOpenChange={(open) => !open && setEditRecord(null)}
        patientId={patientId}
        record={editRecord}
      />

      <SendNalazDialog
        open={sendNalazOpen}
        onOpenChange={setSendNalazOpen}
        patientId={patientId}
        hasCezihIdentifier={hasCezihIdentifier}
        onlyRecordId={sendRecordId}
      />
    </div>
  )
}
