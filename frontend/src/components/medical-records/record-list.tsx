"use client"

import { useState } from "react"
import { PlusIcon, PencilIcon, EyeIcon } from "lucide-react"

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
import { RecordForm } from "./record-form"
import { RecordDetail } from "./record-detail"
import { useMedicalRecords } from "@/lib/hooks/use-medical-records"
import { useRecordTypeMaps } from "@/lib/hooks/use-record-types"
import { usePermissions } from "@/lib/hooks/use-permissions"
import { RECORD_SENSITIVITY, RECORD_SENSITIVITY_COLORS } from "@/lib/constants"
import { formatDateHR } from "@/lib/utils"
import type { MedicalRecord } from "@/lib/types"

interface RecordListProps {
  patientId: string
}

export function RecordList({ patientId }: RecordListProps) {
  const [tipFilter, setTipFilter] = useState<string>("")
  const [formOpen, setFormOpen] = useState(false)
  const [viewRecordId, setViewRecordId] = useState<string | null>(null)
  const [editRecord, setEditRecord] = useState<MedicalRecord | null>(null)

  const { canCreateMedicalRecord, canEditMedicalRecord } = usePermissions()
  const { recordTypes, tipLabelMap, tipColorMap, isCezihMandatory } = useRecordTypeMaps()
  const { data, isLoading } = useMedicalRecords(
    patientId,
    tipFilter || undefined,
  )
  const records = data?.items ?? []
  const viewRecord = viewRecordId ? records.find((r) => r.id === viewRecordId) ?? null : null

  function handleEdit(record: MedicalRecord) {
    setViewRecordId(null)
    setEditRecord(record)
  }

  if (isLoading) {
    return <LoadingSpinner text="Učitavanje..." />
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Select value={tipFilter} onValueChange={(v) => setTipFilter(v ?? "")}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Svi tipovi">
              {tipFilter ? recordTypes.find((rt) => rt.slug === tipFilter)?.label : undefined}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {recordTypes.map((rt) => (
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
          <p className="text-muted-foreground">Nema medicinskih zapisa</p>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Datum</TableHead>
              <TableHead>Tip</TableHead>
              <TableHead className="hidden md:table-cell">Dijagnoza</TableHead>
              <TableHead className="hidden lg:table-cell">Doktor</TableHead>
              <TableHead className="hidden sm:table-cell">CEZIH</TableHead>
              <TableHead className="text-right">Akcije</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {records.map((r) => (
              <TableRow key={r.id}>
                <TableCell>{formatDateHR(r.datum)}</TableCell>
                <TableCell>
                  <div className="flex items-center gap-1">
                    <Badge
                      variant="secondary"
                      className={tipColorMap[r.tip] || ""}
                    >
                      {tipLabelMap[r.tip] || r.tip}
                    </Badge>
                    {isCezihMandatory.has(r.tip) && (
                      <span className="text-[10px] font-medium text-emerald-600" title="Obavezno za CEZIH">CEZIH</span>
                    )}
                  </div>
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
                <TableCell className="hidden sm:table-cell">
                  {r.sensitivity && r.sensitivity !== "standard" && (
                    <Badge
                      variant="secondary"
                      className={`mr-1 ${RECORD_SENSITIVITY_COLORS[r.sensitivity] || ""}`}
                    >
                      {RECORD_SENSITIVITY[r.sensitivity]}
                    </Badge>
                  )}
                  <Badge variant={r.cezih_sent ? "default" : "outline"} className={r.cezih_storno ? "bg-red-100 text-red-800" : r.cezih_sent ? "bg-green-100 text-green-800" : "text-muted-foreground"}>
                    {r.cezih_storno ? "Storniran" : r.cezih_sent ? "Poslan" : "Nije poslan"}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => {
                        setEditRecord(null)
                        setViewRecordId(r.id)
                      }}
                    >
                      <EyeIcon className="h-4 w-4" />
                    </Button>
                    {canEditMedicalRecord && (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => handleEdit(r)}
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

      {viewRecord && (
        <RecordDetail
          open={!!viewRecord}
          onOpenChange={(open) => !open && setViewRecordId(null)}
          record={viewRecord}
          patientId={patientId}
          onEdit={() => handleEdit(viewRecord)}
        />
      )}
    </div>
  )
}
