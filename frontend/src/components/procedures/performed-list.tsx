"use client"

import { useState, useEffect, useMemo } from "react"
import { useForm, Controller, useWatch } from "react-hook-form"
import { z } from "zod"
import { standardSchemaResolver } from "@hookform/resolvers/standard-schema"
import { toast } from "sonner"
import { PlusIcon, FileTextIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
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
import {
  usePerformedProcedures,
  useCreatePerformed,
  useProcedures,
} from "@/lib/hooks/use-procedures"
import { useMedicalRecords } from "@/lib/hooks/use-medical-records"
import { useRecordTypeMaps } from "@/lib/hooks/use-record-types"
import { PredracunDialog } from "@/components/procedures/predracun-dialog"
import { formatDateHR, formatCurrencyEUR } from "@/lib/utils"
import type { PerformedProcedureCreate } from "@/lib/types"

const performedSchema = z.object({
  procedure_id: z.string().min(1, "Postupak je obavezan"),
  datum: z.string().min(1, "Datum je obavezan"),
  cijena_eur: z.coerce.number().min(0).optional(),
  napomena: z.string().optional(),
  medical_record_id: z.string().optional(),
})

type PerformedFormData = z.infer<typeof performedSchema>

const PAGE_SIZE = 20

interface PerformedListProps {
  patientId: string
}

export function PerformedList({ patientId }: PerformedListProps) {
  const [formOpen, setFormOpen] = useState(false)
  const [predracunOpen, setPredracunOpen] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [page, setPage] = useState(0)
  const { data, isLoading } = usePerformedProcedures(patientId, undefined, undefined, undefined, undefined, page * PAGE_SIZE, PAGE_SIZE)
  const { data: proceduresData } = useProcedures(undefined, undefined, 0, 100)
  const { data: recordsData } = useMedicalRecords(patientId)
  const createMutation = useCreatePerformed()
  const { tipLabelMap } = useRecordTypeMaps()

  const procedures = proceduresData?.items ?? []
  const records = recordsData?.items ?? []

  const {
    register,
    handleSubmit,
    reset,
    control,
    formState: { errors },
  } = useForm<PerformedFormData>({
    resolver: standardSchemaResolver(performedSchema),
  })

  const procedureId = useWatch({ control, name: "procedure_id" })
  const selectedProcedure = procedures.find((p) => p.id === procedureId)

  useEffect(() => {
    setSelectedIds(new Set())
  }, [page])

  useEffect(() => {
    if (formOpen) {
      reset({
        procedure_id: "",
        datum: new Date().toISOString().split("T")[0],
        cijena_eur: undefined,
        napomena: undefined,
        medical_record_id: undefined,
      })
    }
  }, [formOpen, reset])

  async function onSubmit(data: PerformedFormData) {
    try {
      const payload: PerformedProcedureCreate = {
        patient_id: patientId,
        procedure_id: data.procedure_id,
        datum: data.datum,
        cijena_cents: data.cijena_eur != null ? Math.round(data.cijena_eur * 100) : undefined,
        napomena: data.napomena || undefined,
        medical_record_id: data.medical_record_id || undefined,
      }
      await createMutation.mutateAsync(payload)
      toast.success("Postupak zabilježen")
      setFormOpen(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Greška pri spremanju")
    }
  }

  const items = useMemo(() => data?.items ?? [], [data?.items])

  const selectedProcedures = useMemo(
    () => items.filter((p) => selectedIds.has(p.id)),
    [items, selectedIds],
  )

  const selectedTotal = selectedProcedures.reduce((sum, p) => sum + p.cijena_cents, 0)

  const { sorted: sortedItems, sortKey: pSortKey, sortDir: pSortDir, toggleSort: togglePSort } = useTableSort(items, {
    defaultKey: "datum",
    defaultDir: "desc",
    keyAccessors: {
      postupak: (p) => `${p.procedure_sifra ?? ""} ${p.procedure_naziv ?? ""}`.trim(),
      doktor: (p) => `${p.doktor_prezime ?? ""} ${p.doktor_ime ?? ""}`.trim(),
      cijena: (p) => p.cijena_cents,
      napomena: (p) => p.napomena || "",
    },
  })

  if (isLoading) {
    return <LoadingSpinner text="Učitavanje..." />
  }

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (selectedIds.size === items.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(items.map((p) => p.id)))
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div>
          {selectedIds.size > 0 && (
            <Button
              variant="outline"
              onClick={() => setPredracunOpen(true)}
            >
              <FileTextIcon className="mr-2 h-4 w-4" />
              Predračun ({selectedIds.size} — {formatCurrencyEUR(selectedTotal / 100)})
            </Button>
          )}
        </div>
        <Button onClick={() => setFormOpen(true)}>
          <PlusIcon className="mr-2 h-4 w-4" />
          Dodaj postupak
        </Button>
      </div>

      {items.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-12">
          <p className="text-muted-foreground">Nema izvršenih postupaka</p>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <Checkbox
                  checked={items.length > 0 && selectedIds.size === items.length}
                  onCheckedChange={toggleAll}
                />
              </TableHead>
              <SortableTableHead columnKey="datum" label="Datum" currentKey={pSortKey} currentDir={pSortDir} onSort={togglePSort} />
              <SortableTableHead columnKey="postupak" label="Postupak" currentKey={pSortKey} currentDir={pSortDir} onSort={togglePSort} />
              <SortableTableHead columnKey="doktor" label="Doktor" currentKey={pSortKey} currentDir={pSortDir} onSort={togglePSort} className="hidden md:table-cell" />
              <SortableTableHead columnKey="cijena" label="Cijena" currentKey={pSortKey} currentDir={pSortDir} onSort={togglePSort} className="hidden sm:table-cell text-right" />
              <SortableTableHead columnKey="napomena" label="Napomena" currentKey={pSortKey} currentDir={pSortDir} onSort={togglePSort} className="hidden lg:table-cell" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedItems.map((p) => (
              <TableRow key={p.id} data-state={selectedIds.has(p.id) ? "selected" : undefined}>
                <TableCell>
                  <Checkbox
                    checked={selectedIds.has(p.id)}
                    onCheckedChange={() => toggleSelect(p.id)}
                  />
                </TableCell>
                <TableCell>{formatDateHR(p.datum)}</TableCell>
                <TableCell>
                  <span className="font-mono text-xs text-muted-foreground">
                    {p.procedure_sifra}
                  </span>{" "}
                  <span className="font-medium">{p.procedure_naziv}</span>
                </TableCell>
                <TableCell className="hidden md:table-cell">
                  {p.doktor_prezime
                    ? `${p.doktor_ime} ${p.doktor_prezime}`
                    : "—"}
                </TableCell>
                <TableCell className="hidden sm:table-cell text-right">
                  {formatCurrencyEUR(p.cijena_cents / 100)}
                </TableCell>
                <TableCell className="hidden lg:table-cell max-w-[200px] truncate">
                  {p.napomena || "—"}
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

      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Dodaj izvršeni postupak</DialogTitle>
            <DialogDescription>
              Odaberite postupak i unesite podatke
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-2">
              <Label>Postupak *</Label>
              <Controller
                name="procedure_id"
                control={control}
                render={({ field }) => {
                  const selectedProcedure = procedures.find((p) => p.id === field.value)
                  return (
                    <Select value={field.value ?? ""} onValueChange={field.onChange}>
                      <SelectTrigger>
                        <SelectValue placeholder="Odaberite postupak">
                          {selectedProcedure
                            ? `[${selectedProcedure.sifra}] ${selectedProcedure.naziv} — ${formatCurrencyEUR(selectedProcedure.cijena_cents / 100)}`
                            : undefined}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent className="min-w-[400px]">
                        {procedures.map((p) => (
                          <SelectItem key={p.id} value={p.id}>
                            [{p.sifra}] {p.naziv} — {formatCurrencyEUR(p.cijena_cents / 100)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )
                }}
              />
              {errors.procedure_id && (
                <p className="text-sm text-destructive">{errors.procedure_id.message}</p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="datum">Datum *</Label>
                <Input id="datum" type="date" {...register("datum")} />
                {errors.datum && (
                  <p className="text-sm text-destructive">{errors.datum.message}</p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="cijena">Cijena (EUR)</Label>
                <Input
                  id="cijena"
                  type="number"
                  step="0.01"
                  min="0"
                  placeholder={
                    selectedProcedure
                      ? String(selectedProcedure.cijena_cents / 100)
                      : "Prema katalogu"
                  }
                  {...register("cijena_eur", { valueAsNumber: true })}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="napomena">Napomena</Label>
              <Textarea
                id="napomena"
                placeholder="Dodatne napomene..."
                {...register("napomena")}
              />
            </div>

            {records.length > 0 && (
              <div className="space-y-2">
                <Label>Povezani nalaz (opcionalno)</Label>
                <Controller
                  name="medical_record_id"
                  control={control}
                  render={({ field }) => (
                    <Select
                      value={field.value ?? ""}
                      onValueChange={(v) => field.onChange(v === "none" ? "" : (v ?? ""))}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Bez povezanog nalaza">
                          {(() => {
                            const rid = field.value
                            if (!rid) return undefined
                            const r = records.find((rec) => rec.id === rid)
                            return r
                              ? `${formatDateHR(r.datum)} — ${tipLabelMap[r.tip] || r.tip}${r.dijagnoza_mkb ? ` (${r.dijagnoza_mkb})` : ""}`
                              : undefined
                          })()}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">Bez povezanog nalaza</SelectItem>
                        {records.map((r) => (
                          <SelectItem key={r.id} value={r.id}>
                            {formatDateHR(r.datum)} — {tipLabelMap[r.tip] || r.tip}
                            {r.dijagnoza_mkb ? ` (${r.dijagnoza_mkb})` : ""}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={() => setFormOpen(false)}>
                Odustani
              </Button>
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? "Spremanje..." : "Zabilježi"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <PredracunDialog
        open={predracunOpen}
        onOpenChange={setPredracunOpen}
        patientId={patientId}
        selectedProcedures={selectedProcedures}
        onSuccess={() => setSelectedIds(new Set())}
      />
    </div>
  )
}
