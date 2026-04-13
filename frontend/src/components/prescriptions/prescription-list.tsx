"use client"

import { useState } from "react"
import { PlusIcon, EyeIcon, Send, Trash2 } from "lucide-react"
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
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { TablePagination } from "@/components/shared/table-pagination"
import { PrescriptionForm } from "./prescription-form"
import { PrescriptionDetail } from "./prescription-detail"
import { usePrescriptions, useSendPrescription, useDeletePrescription } from "@/lib/hooks/use-prescriptions"
import { usePermissions } from "@/lib/hooks/use-permissions"
import { formatDateTimeHR } from "@/lib/utils"
import type { Prescription } from "@/lib/types"

const PAGE_SIZE = 20

interface PrescriptionListProps {
  patientId: string
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

export function PrescriptionList({ patientId }: PrescriptionListProps) {
  const [statusFilter, setStatusFilter] = useState("")
  const [page, setPage] = useState(0)
  const [formOpen, setFormOpen] = useState(false)
  const [viewId, setViewId] = useState<string | null>(null)

  const { canPerformCezihOps, canUseHzzo } = usePermissions()
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

  if (isLoading) {
    return <LoadingSpinner text="Učitavanje..." />
  }

  const handleQuickSend = (p: Prescription) => {
    sendPrescription.mutate(p.id, {
      onSuccess: (res) => toast.success(`e-Recept poslan (${res.cezih_recept_id})`),
      onError: (err) => toast.error(err.message),
    })
  }

  const handleQuickDelete = (p: Prescription) => {
    deletePrescription.mutate(p.id, {
      onSuccess: () => toast.success("Nacrt recepta obrisan"),
      onError: (err) => toast.error(err.message),
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
              <TableHead>Datum</TableHead>
              <TableHead>Lijekovi</TableHead>
              <TableHead className="hidden lg:table-cell">Doktor</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Akcije</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {prescriptions.map((p) => {
              const drugNames = p.lijekovi.map((l) => l.naziv).join(", ")
              const isDraft = !p.cezih_sent
              return (
                <TableRow key={p.id}>
                  <TableCell className="text-sm">{formatDateTimeHR(p.created_at)}</TableCell>
                  <TableCell className="text-sm max-w-[250px] truncate" title={drugNames}>
                    {drugNames || "—"}
                  </TableCell>
                  <TableCell className="hidden lg:table-cell text-sm">
                    {p.doktor_prezime ? `${p.doktor_ime} ${p.doktor_prezime}` : "—"}
                  </TableCell>
                  <TableCell>{statusBadge(p)}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => setViewId(p.id)}
                      >
                        <EyeIcon className="h-4 w-4" />
                      </Button>
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
