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
import { RECORD_TIP_OPTIONS, RECORD_TIP_COLORS } from "@/lib/constants"
import { formatDateHR } from "@/lib/utils"
import type { MedicalRecord } from "@/lib/types"

interface RecordListProps {
  patientId: string
}

export function RecordList({ patientId }: RecordListProps) {
  const [tipFilter, setTipFilter] = useState<string>("")
  const [formOpen, setFormOpen] = useState(false)
  const [viewRecord, setViewRecord] = useState<MedicalRecord | null>(null)
  const [editRecord, setEditRecord] = useState<MedicalRecord | null>(null)

  const { data, isLoading } = useMedicalRecords(
    patientId,
    tipFilter || undefined,
  )
  function handleEdit(record: MedicalRecord) {
    setViewRecord(null)
    setEditRecord(record)
  }

  if (isLoading) {
    return <LoadingSpinner text="Učitavanje..." />
  }

  const records = data?.items ?? []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Select value={tipFilter} onValueChange={(v) => setTipFilter(v ?? "")}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Svi tipovi" />
          </SelectTrigger>
          <SelectContent>
            {RECORD_TIP_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button onClick={() => setFormOpen(true)}>
          <PlusIcon className="mr-2 h-4 w-4" />
          Novi nalaz
        </Button>
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
                  <Badge
                    variant="secondary"
                    className={RECORD_TIP_COLORS[r.tip] || ""}
                  >
                    {r.tip}
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
                <TableCell className="hidden sm:table-cell">
                  <Badge variant={r.cezih_sent ? "default" : "outline"} className={r.cezih_sent ? "bg-green-100 text-green-800" : "text-muted-foreground"}>
                    {r.cezih_sent ? "Poslan" : "Nije poslan"}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => {
                        setEditRecord(null)
                        setViewRecord(r)
                      }}
                    >
                      <EyeIcon className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => handleEdit(r)}
                    >
                      <PencilIcon className="h-4 w-4" />
                    </Button>
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
          onOpenChange={(open) => !open && setViewRecord(null)}
          record={viewRecord}
          patientId={patientId}
          onEdit={() => handleEdit(viewRecord)}
        />
      )}
    </div>
  )
}
