"use client"
/* eslint-disable react-hooks/incompatible-library -- react-hook-form watch() is intentionally used */

import { useEffect } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { standardSchemaResolver } from "@hookform/resolvers/standard-schema"
import { toast } from "sonner"

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
import { PROCEDURE_KATEGORIJA_OPTIONS } from "@/lib/constants"
import {
  useCreateProcedure,
  useUpdateProcedure,
} from "@/lib/hooks/use-procedures"
import type { Procedure, ProcedureCreate } from "@/lib/types"

const procedureSchema = z.object({
  sifra: z.string().min(1, "Šifra je obavezna").max(20),
  naziv: z.string().min(1, "Naziv je obavezan").max(255),
  opis: z.string().optional(),
  cijena_eur: z.coerce.number({ message: "Cijena je obavezna" }).min(0, "Cijena ne može biti negativna"),
  trajanje_minuta: z.coerce.number({ message: "Trajanje je obavezno" }).min(5, "Min 5 min").max(480, "Max 480 min"),
  kategorija: z.string().min(1, "Kategorija je obavezna"),
})

type ProcedureFormData = z.infer<typeof procedureSchema>

interface ProcedureFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  procedure?: Procedure
}

export function ProcedureForm({ open, onOpenChange, procedure }: ProcedureFormProps) {
  const isEdit = !!procedure
  const createMutation = useCreateProcedure()
  const updateMutation = useUpdateProcedure()

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { errors },
  } = useForm<ProcedureFormData>({
    resolver: standardSchemaResolver(procedureSchema),
  })

  const kategorijaValue = watch("kategorija")

  useEffect(() => {
    if (open) {
      if (procedure) {
        reset({
          sifra: procedure.sifra,
          naziv: procedure.naziv,
          opis: procedure.opis ?? undefined,
          cijena_eur: procedure.cijena_cents / 100,
          trajanje_minuta: procedure.trajanje_minuta,
          kategorija: procedure.kategorija,
        })
      } else {
        reset({
          sifra: "",
          naziv: "",
          opis: undefined,
          cijena_eur: 0,
          trajanje_minuta: 30,
          kategorija: "",
        })
      }
    }
  }, [open, procedure, reset])

  async function onSubmit(data: ProcedureFormData) {
    try {
      const payload: ProcedureCreate = {
        sifra: data.sifra,
        naziv: data.naziv,
        opis: data.opis || null,
        cijena_cents: Math.round(data.cijena_eur * 100),
        trajanje_minuta: data.trajanje_minuta,
        kategorija: data.kategorija,
      }

      if (isEdit && procedure) {
        await updateMutation.mutateAsync({ id: procedure.id, data: payload })
        toast.success("Postupak ažuriran")
      } else {
        await createMutation.mutateAsync(payload)
        toast.success("Postupak kreiran")
      }
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Greška pri spremanju")
    }
  }

  const isSubmitting = createMutation.isPending || updateMutation.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Uredi postupak" : "Novi postupak"}</DialogTitle>
          <DialogDescription>
            {isEdit ? "Promijenite podatke o postupku" : "Dodajte novi postupak u katalog"}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="sifra">Šifra *</Label>
              <Input id="sifra" placeholder="npr. D001" {...register("sifra")} />
              {errors.sifra && (
                <p className="text-sm text-destructive">{errors.sifra.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label>Kategorija *</Label>
              <Select
                value={kategorijaValue ?? ""}
                onValueChange={(v) => setValue("kategorija", v ?? "")}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Odaberite kategoriju">
                    {PROCEDURE_KATEGORIJA_OPTIONS.find((o) => o.value === kategorijaValue)?.label}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {PROCEDURE_KATEGORIJA_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {errors.kategorija && (
                <p className="text-sm text-destructive">{errors.kategorija.message}</p>
              )}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="naziv">Naziv *</Label>
            <Input id="naziv" placeholder="Naziv postupka" {...register("naziv")} />
            {errors.naziv && (
              <p className="text-sm text-destructive">{errors.naziv.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="opis">Opis</Label>
            <Textarea
              id="opis"
              placeholder="Opcionalni opis postupka..."
              {...register("opis")}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="cijena">Cijena (EUR)</Label>
              <Input
                id="cijena"
                type="number"
                step="0.01"
                min="0"
                {...register("cijena_eur", { valueAsNumber: true })}
              />
              {errors.cijena_eur && (
                <p className="text-sm text-destructive">{errors.cijena_eur.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="trajanje">Trajanje (min)</Label>
              <Input
                id="trajanje"
                type="number"
                min="5"
                max="480"
                {...register("trajanje_minuta", { valueAsNumber: true })}
              />
              {errors.trajanje_minuta && (
                <p className="text-sm text-destructive">{errors.trajanje_minuta.message}</p>
              )}
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Odustani
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting
                ? "Spremanje..."
                : isEdit
                  ? "Ažuriraj"
                  : "Kreiraj"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
