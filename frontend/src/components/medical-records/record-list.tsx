"use client"

import { useState } from "react"
import { PlusIcon, PencilIcon, Send, Info } from "lucide-react"

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
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
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

const PAGE_SIZE = 20

interface RecordListProps {
  patientId: string
  patientMbo?: string | null
}

export function RecordList({ patientId, patientMbo }: RecordListProps) {
  const [tipFilter, setTipFilter] = useState<string>("")
  const [page, setPage] = useState(0)
  const [formOpen, setFormOpen] = useState(false)
  const [editRecord, setEditRecord] = useState<MedicalRecord | null>(null)
  const [sendNalazOpen, setSendNalazOpen] = useState(false)
  const [sendRecordId, setSendRecordId] = useState<string | undefined>()

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
              <TableHead>Datum</TableHead>
              <TableHead>Tip</TableHead>
              <TableHead className="hidden md:table-cell">Dijagnoza</TableHead>
              <TableHead className="hidden lg:table-cell">Doktor</TableHead>
              <TableHead>
                <div className="flex items-center gap-1">
                  <span>Status e-Nalaza</span>
                  <Popover>
                    <PopoverTrigger
                      aria-label="Objašnjenje statusa e-Nalaza"
                      className="text-muted-foreground hover:text-foreground"
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
            {records.map((r) => (
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
        patientMbo={patientMbo ?? null}
        onlyRecordId={sendRecordId}
      />
    </div>
  )
}
