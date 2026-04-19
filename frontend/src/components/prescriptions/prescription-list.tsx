"use client"

import { useState } from "react"
import { PlusIcon, EyeIcon, PencilIcon, Send, Trash2 } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
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
import { SortableTableHead } from "@/components/ui/sortable-table-head"
import { useTableSort } from "@/lib/hooks/use-table-sort"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { TablePagination } from "@/components/shared/table-pagination"
import { PrescriptionForm } from "./prescription-form"
import { PrescriptionDetail } from "./prescription-detail"
import { usePrescriptions, useSendPrescription, useDeletePrescription } from "@/lib/hooks/use-prescriptions"
import { usePermissions } from "@/lib/hooks/use-permissions"
import { useRecordTypeMaps } from "@/lib/hooks/use-record-types"
import { formatDateHR, formatDateTimeHR } from "@/lib/utils"
import type { Prescription } from "@/lib/types"

const PAGE_SIZE = 20

interface PrescriptionListProps {
  patientId: string
  onOpenNalaz?: (recordId: string) => void
}

const STATUS_OPTIONS = [
  { value: "all", label: "Svi statusi" },
  { value: "nacrt", label: "Nacrt" },
  { value: "aktivan", label: "Poslan" },
  { value: "storniran", label: "Storniran" },
]

function statusBadge(p: Prescription) {
  if (p.cezih_storno) return <Badge className="bg-red-100 text-red-800">Storniran</Badge>
  if (p.cezih_sent) return <Badge className="bg-green-100 text-green-800">Poslan</Badge>
  return <Badge variant="outline" className="text-muted-foreground">Nacrt</Badge>
}

function sourceNalazLabel(p: Prescription, tipLabelMap: Record<string, string>) {
  const parts: string[] = []
  if (p.medical_record_tip) parts.push(tipLabelMap[p.medical_record_tip] ?? p.medical_record_tip)
  const dx = p.medical_record_dijagnoza_tekst?.trim() || p.medical_record_dijagnoza_mkb?.trim()
  if (dx) parts.push(dx)
  if (p.medical_record_datum) parts.push(formatDateHR(p.medical_record_datum))
  return parts.join(" · ")
}

export function PrescriptionList({ patientId, onOpenNalaz }: PrescriptionListProps) {
  const [statusFilter, setStatusFilter] = useState("")
  const [page, setPage] = useState(0)
  const [formOpen, setFormOpen] = useState(false)
  const [editPrescription, setEditPrescription] = useState<Prescription | null>(null)
  const [viewId, setViewId] = useState<string | null>(null)

  const { canPerformCezihOps, canUseHzzo } = usePermissions()
  const { tipLabelMap } = useRecordTypeMaps()
  const { data, isLoading } = usePrescriptions(
    patientId,
    statusFilter && statusFilter !== "all" ? statusFilter : undefined,
    page * PAGE_SIZE,
    PAGE_SIZE,
  )
  const sendPrescription = useSendPrescription()
  const deletePrescription = useDeletePrescription()

  const prescriptions = data?.items ?? []
  const viewPrescription = viewId ? prescriptions.find((p) => p.id === viewId) ?? null : null

  const { sorted: sortedPrescriptions, sortKey: rxSortKey, sortDir: rxSortDir, toggleSort: toggleRxSort } = useTableSort(prescriptions, {
    defaultKey: "created_at",
    defaultDir: "desc",
    keyAccessors: {
      lijekovi: (p: Prescription) => p.lijekovi.map((l) => l.naziv).join(", "),
      doktor: (p: Prescription) => `${p.doktor_prezime ?? ""} ${p.doktor_ime ?? ""}`.trim(),
      status: (p: Prescription) => (p.cezih_storno ? 2 : p.cezih_sent ? 1 : 0),
    },
  })

  if (isLoading) {
    return <LoadingSpinner text="Učitavanje..." />
  }

  const handleQuickSend = (p: Prescription) => {
    sendPrescription.mutate(p.id, {
      onSuccess: (res) => toast.success(`e-Recept poslan (${res.cezih_recept_id})`),
    })
  }

  const handleQuickDelete = (p: Prescription) => {
    deletePrescription.mutate(p.id, {
      onSuccess: () => toast.success("Nacrt recepta obrisan"),
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v ?? ""); setPage(0) }}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Svi statusi">
              {statusFilter ? STATUS_OPTIONS.find((o) => o.value === statusFilter)?.label : undefined}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {canPerformCezihOps && (
          <Button onClick={() => setFormOpen(true)}>
            <PlusIcon className="mr-2 h-4 w-4" />
            Novi recept
          </Button>
        )}
      </div>

      {prescriptions.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-12">
          <p className="text-muted-foreground">Nema recepata</p>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <SortableTableHead columnKey="created_at" label="Datum" currentKey={rxSortKey} currentDir={rxSortDir} onSort={toggleRxSort} />
              <SortableTableHead columnKey="lijekovi" label="Lijekovi" currentKey={rxSortKey} currentDir={rxSortDir} onSort={toggleRxSort} />
              <SortableTableHead columnKey="doktor" label="Doktor" currentKey={rxSortKey} currentDir={rxSortDir} onSort={toggleRxSort} className="hidden lg:table-cell" />
              <SortableTableHead columnKey="status" label="Status" currentKey={rxSortKey} currentDir={rxSortDir} onSort={toggleRxSort} />
              <TableHead className="text-right">Akcije</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedPrescriptions.map((p) => {
              const drugNames = p.lijekovi.map((l) => l.naziv).join(", ")
              const isDraft = !p.cezih_sent
              const sourceLabel = p.medical_record_id ? sourceNalazLabel(p, tipLabelMap) : ""
              return (
                <TableRow key={p.id}>
                  <TableCell className="text-sm">{formatDateTimeHR(p.created_at)}</TableCell>
                  <TableCell className="text-sm max-w-[250px] truncate" title={drugNames}>
                    {drugNames || "—"}
                  </TableCell>
                  <TableCell className="hidden lg:table-cell text-sm">
                    {p.doktor_prezime ? `${p.doktor_ime} ${p.doktor_prezime}` : "—"}
                  </TableCell>
                  <TableCell>
                    <div className="space-y-1">
                      {statusBadge(p)}
                      {p.medical_record_id && sourceLabel && (
                        <button
                          type="button"
                          onClick={() => onOpenNalaz?.(p.medical_record_id!)}
                          className="block text-left text-xs text-muted-foreground hover:text-foreground hover:underline max-w-[280px] truncate"
                          title={sourceLabel}
                          disabled={!onOpenNalaz}
                        >
                          Iz nalaza: {sourceLabel}
                        </button>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => setViewId(p.id)}
                      >
                        <EyeIcon className="h-4 w-4" />
                      </Button>
                      {isDraft && canPerformCezihOps && (
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onClick={() => setEditPrescription(p)}
                          title="Uredi recept"
                        >
                          <PencilIcon className="h-4 w-4" />
                        </Button>
                      )}
                      {isDraft && canPerformCezihOps && canUseHzzo && (
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => handleQuickSend(p)}
                            disabled={sendPrescription.isPending}
                            title="Pošalji na CEZIH"
                          >
                            <Send className="h-4 w-4" />
                          </Button>
                        )}
                        {isDraft && (
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => handleQuickDelete(p)}
                            disabled={deletePrescription.isPending}
                            title="Obriši nacrt"
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        )}
                    </div>
                  </TableCell>
                </TableRow>
              )
            })}
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

      <PrescriptionForm
        open={formOpen}
        onOpenChange={setFormOpen}
        patientId={patientId}
      />

      <PrescriptionForm
        open={!!editPrescription}
        onOpenChange={(open) => !open && setEditPrescription(null)}
        patientId={patientId}
        prescription={editPrescription}
      />

      {viewPrescription && (
        <PrescriptionDetail
          open={!!viewPrescription}
          onOpenChange={(open) => !open && setViewId(null)}
          prescription={viewPrescription}
        />
      )}
    </div>
  )
}
