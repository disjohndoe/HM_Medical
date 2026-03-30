"use client"
/* eslint-disable react-hooks/incompatible-library -- react-hook-form watch() is intentionally used */

import { useState, useEffect } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { standardSchemaResolver } from "@hookform/resolvers/standard-schema"
import { toast } from "sonner"
import { PlusIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
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
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import {
  usePerformedProcedures,
  useCreatePerformed,
  useProcedures,
} from "@/lib/hooks/use-procedures"
import { formatDateHR, formatCurrencyEUR } from "@/lib/utils"
import type { PerformedProcedureCreate } from "@/lib/types"

const performedSchema = z.object({
  procedure_id: z.string().min(1, "Postupak je obavezan"),
  datum: z.string().min(1, "Datum je obavezan"),
  cijena_eur: z.number().min(0).optional(),
  napomena: z.string().optional(),
})

type PerformedFormData = z.infer<typeof performedSchema>

interface PerformedListProps {
  patientId: string
}

export function PerformedList({ patientId }: PerformedListProps) {
  const [formOpen, setFormOpen] = useState(false)
  const { data, isLoading } = usePerformedProcedures(patientId)
  const { data: proceduresData } = useProcedures(undefined, undefined, 0, 100)
  const createMutation = useCreatePerformed()

  const procedures = proceduresData?.items ?? []

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { errors },
  } = useForm<PerformedFormData>({
    resolver: standardSchemaResolver(performedSchema),
  })

  const procedureId = watch("procedure_id")

  const selectedProcedure = procedures.find((p) => p.id === procedureId)

  useEffect(() => {
    if (formOpen) {
      reset({
        procedure_id: "",
        datum: new Date().toISOString().split("T")[0],
        cijena_eur: undefined,
        napomena: undefined,
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
      }
      await createMutation.mutateAsync(payload)
      toast.success("Postupak zabilježen")
      setFormOpen(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Greška pri spremanju")
    }
  }

  if (isLoading) {
    return <LoadingSpinner text="Učitavanje..." />
  }

  const items = data?.items ?? []

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
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
              <TableHead>Datum</TableHead>
              <TableHead>Postupak</TableHead>
              <TableHead className="hidden md:table-cell">Doktor</TableHead>
              <TableHead className="hidden sm:table-cell text-right">Cijena</TableHead>
              <TableHead className="hidden lg:table-cell">Napomena</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((p) => (
              <TableRow key={p.id}>
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
              <Select
                value={procedureId ?? ""}
                onValueChange={(v) => setValue("procedure_id", v ?? "")}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Odaberite postupak" />
                </SelectTrigger>
                <SelectContent>
                  {procedures.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      [{p.sifra}] {p.naziv} — {formatCurrencyEUR(p.cijena_cents / 100)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
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
    </div>
  )
}
