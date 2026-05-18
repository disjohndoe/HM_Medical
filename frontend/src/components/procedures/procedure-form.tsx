"use client"

import { useEffect, useState, useRef } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { standardSchemaResolver } from "@hookform/resolvers/standard-schema"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { useDtsSearch } from "@/lib/hooks/use-cezih"
import {
  useCreateProcedure,
  useUpdateProcedure,
} from "@/lib/hooks/use-procedures"
import type { Procedure, ProcedureCreate, CodeSystemItem } from "@/lib/types"

const procedureSchema = z.object({
  cijena_eur: z.coerce.number({ message: "Cijena je obavezna" }).min(0, "Cijena ne može biti negativna"),
  trajanje_minuta: z.coerce.number({ message: "Trajanje je obavezno" }).min(5, "Min 5 min").max(480, "Max 480 min"),
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

  const [dtsQuery, setDtsQuery] = useState("")
  const [selectedDts, setSelectedDts] = useState<CodeSystemItem | null>(null)
  const [showDropdown, setShowDropdown] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const { data: dtsResults = [], isLoading: dtsLoading } = useDtsSearch(dtsQuery)

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ProcedureFormData>({
    resolver: standardSchemaResolver(procedureSchema),
  })

  const [prevOpen, setPrevOpen] = useState(open)
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) {
      if (procedure) {
        setSelectedDts({
          code: procedure.dts_code ?? procedure.sifra,
          display: procedure.dts_display ?? procedure.naziv,
          system: "",
        })
        setDtsQuery("")
        reset({
          cijena_eur: procedure.cijena_cents / 100,
          trajanje_minuta: procedure.trajanje_minuta,
        })
      } else {
        setSelectedDts(null)
        setDtsQuery("")
        reset({ cijena_eur: 0, trajanje_minuta: 30 })
      }
    }
  }

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false)
      }
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [])

  async function onSubmit(data: ProcedureFormData) {
    if (!isEdit && !selectedDts) {
      toast.error("Odaberite DTS šifru")
      return
    }

    try {
      if (isEdit && procedure) {
        await updateMutation.mutateAsync({
          id: procedure.id,
          data: {
            cijena_cents: Math.round(data.cijena_eur * 100),
            trajanje_minuta: data.trajanje_minuta,
          },
        })
        toast.success("Postupak ažuriran")
      } else if (selectedDts) {
        const payload: ProcedureCreate = {
          dts_code: selectedDts.code,
          cijena_cents: Math.round(data.cijena_eur * 100),
          trajanje_minuta: data.trajanje_minuta,
        }
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
            {isEdit ? "Promijenite cijenu i trajanje postupka" : "Dodajte DTS postupak iz HZZO šifrarnika"}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {isEdit ? (
            <div className="space-y-2">
              <Label>DTS šifra</Label>
              <div className="rounded-md border px-3 py-2 bg-muted">
                <span className="font-mono text-sm">{selectedDts?.code}</span>
                <span className="mx-2 text-muted-foreground">—</span>
                <span className="text-sm">{selectedDts?.display}</span>
              </div>
            </div>
          ) : (
            <div className="space-y-2" ref={dropdownRef}>
              <Label>DTS šifra *</Label>
              {selectedDts ? (
                <div className="flex items-center justify-between rounded-md border px-3 py-2 bg-muted">
                  <div>
                    <span className="font-mono text-sm">{selectedDts.code}</span>
                    <span className="mx-2 text-muted-foreground">—</span>
                    <span className="text-sm">{selectedDts.display}</span>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => { setSelectedDts(null); setDtsQuery(""); }}
                  >
                    Promijeni
                  </Button>
                </div>
              ) : (
                <div className="relative">
                  <Input
                    placeholder="Pretražite DTS postupke (npr. EEG, pregled)..."
                    value={dtsQuery}
                    onChange={(e) => { setDtsQuery(e.target.value); setShowDropdown(true); }}
                    onFocus={() => setShowDropdown(true)}
                  />
                  {dtsLoading && (
                    <div className="absolute right-2 top-2.5">
                      <LoadingSpinner />
                    </div>
                  )}
                  {showDropdown && dtsQuery.length >= 2 && !selectedDts && (
                    <div className="absolute z-50 mt-1 w-full max-h-60 overflow-auto rounded-md border bg-popover shadow-md">
                      {dtsResults.length === 0 && !dtsLoading && (
                        <div className="px-3 py-2 text-sm text-muted-foreground">Nema rezultata</div>
                      )}
                      {dtsResults.map((item) => (
                        <button
                          key={item.code}
                          type="button"
                          className="flex w-full items-start gap-2 px-3 py-2 text-sm hover:bg-accent text-left"
                          onClick={() => { setSelectedDts(item); setShowDropdown(false); setDtsQuery(""); }}
                        >
                          <span className="font-mono text-xs text-muted-foreground shrink-0">{item.code}</span>
                          <span className="line-clamp-2">{item.display}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

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
