"use client"
/* eslint-disable react-hooks/refs -- react-hook-form handleSubmit is a standard pattern that accesses refs internally */

import { useEffect, useRef, useCallback } from "react"
import { useForm, Controller } from "react-hook-form"
import { z } from "zod"
import { standardSchemaResolver } from "@hookform/resolvers/standard-schema"
import { toast } from "sonner"
import { X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { BILJESKA_KATEGORIJA } from "@/lib/constants"
import { useCreateBiljeska, useUpdateBiljeska } from "@/lib/hooks/use-biljeske"
import type { Biljeska, BiljeskaCreate, BiljeskaUpdate } from "@/lib/types"

const biljeskaSchema = z.object({
  datum: z.string().min(1, "Datum je obavezan"),
  naslov: z.string().min(1, "Naslov je obavezan"),
  sadrzaj: z.string().min(3, "Sadržaj mora imati najmanje 3 znaka"),
  kategorija: z.string().min(1, "Kategorija je obavezna"),
})

type BiljeskaFormData = z.infer<typeof biljeskaSchema>

interface BiljeskaFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  patientId: string
  biljeska?: Biljeska | null
}

export function BiljeskaForm({ open, onOpenChange, patientId, biljeska }: BiljeskaFormProps) {
  const isEdit = !!biljeska
  const createMutation = useCreateBiljeska()
  const updateMutation = useUpdateBiljeska()
  const dialogRef = useRef<HTMLDialogElement>(null)

  const {
    register,
    handleSubmit,
    reset,
    control,
    formState: { errors },
  } = useForm<BiljeskaFormData>({
    resolver: standardSchemaResolver(biljeskaSchema),
  })

  useEffect(() => {
    const el = dialogRef.current
    if (!el) return
    if (open && !el.open) el.showModal()
    else if (!open && el.open) el.close()
  }, [open])

  const handleNativeClose = useCallback(() => {
    onOpenChange(false)
  }, [onOpenChange])

  useEffect(() => {
    const el = dialogRef.current
    if (!el) return
    el.addEventListener("close", handleNativeClose)
    return () => el.removeEventListener("close", handleNativeClose)
  }, [handleNativeClose])

  const handleBackdropClick = useCallback((e: React.MouseEvent<HTMLDialogElement>) => {
    if (e.target === dialogRef.current) {
      dialogRef.current?.close()
      onOpenChange(false)
    }
  }, [onOpenChange])

  useEffect(() => {
    if (open) {
      if (biljeska) {
        reset({
          datum: biljeska.datum.split("T")[0],
          naslov: biljeska.naslov,
          sadrzaj: biljeska.sadrzaj,
          kategorija: biljeska.kategorija,
        })
      } else {
        reset({
          datum: new Date().toISOString().split("T")[0],
          naslov: "",
          sadrzaj: "",
          kategorija: "opca",
        })
      }
    }
  }, [open, biljeska, reset])

  async function onSubmit(data: BiljeskaFormData) {
    try {
      if (isEdit && biljeska) {
        const payload: BiljeskaUpdate = {
          datum: data.datum,
          naslov: data.naslov,
          sadrzaj: data.sadrzaj,
          kategorija: data.kategorija,
        }
        await updateMutation.mutateAsync({ id: biljeska.id, data: payload })
        toast.success("Bilješka ažurirana")
      } else {
        const payload: BiljeskaCreate = {
          patient_id: patientId,
          datum: data.datum,
          naslov: data.naslov,
          sadrzaj: data.sadrzaj,
          kategorija: data.kategorija,
        }
        await createMutation.mutateAsync(payload)
        toast.success("Bilješka kreirana")
      }
      onOpenChange(false)
      dialogRef.current?.close()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Greška pri spremanju")
    }
  }

  const isSubmitting = createMutation.isPending || updateMutation.isPending

  const handleClose = () => {
    onOpenChange(false)
    dialogRef.current?.close()
  }

  return (
    <dialog
      ref={dialogRef}
      onClick={handleBackdropClick}
      aria-labelledby="biljeska-form-title"
      className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-[calc(100%-2rem)] sm:max-w-lg max-h-[90vh] overflow-y-auto rounded-xl bg-popover p-4 text-sm text-popover-foreground ring-1 ring-foreground/10 shadow-lg backdrop:bg-black/10 backdrop:backdrop-blur-xs m-0"
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 id="biljeska-form-title" className="font-heading text-base font-medium">
              {isEdit ? "Uredi bilješku" : "Nova bilješka"}
            </h2>
            <p className="text-muted-foreground text-sm">
              {isEdit ? "Promijenite podatke bilješke" : "Kreirajte novu kliničku bilješku"}
            </p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="rounded-md p-1 hover:bg-muted transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="biljeska-datum">Datum *</Label>
              <Input id="biljeska-datum" type="date" disabled={isEdit} {...register("datum")} />
              {errors.datum && (
                <p className="text-sm text-destructive">{errors.datum.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label>Kategorija *</Label>
              <Controller
                name="kategorija"
                control={control}
                render={({ field }) => (
                  <select
                    value={field.value ?? "opca"}
                    onChange={field.onChange}
                    className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm appearance-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
                  >
                    {Object.entries(BILJESKA_KATEGORIJA).map(([slug, label]) => (
                      <option key={slug} value={slug}>{label}</option>
                    ))}
                  </select>
                )}
              />
              {errors.kategorija && (
                <p className="text-sm text-destructive">{errors.kategorija.message}</p>
              )}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="biljeska-naslov">Naslov *</Label>
            <Input id="biljeska-naslov" placeholder="Kratki opis bilješke" {...register("naslov")} />
            {errors.naslov && (
              <p className="text-sm text-destructive">{errors.naslov.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="biljeska-sadrzaj">Sadržaj *</Label>
            <Textarea
              id="biljeska-sadrzaj"
              placeholder="Unesite sadržaj bilješke..."
              className="min-h-[150px]"
              {...register("sadrzaj")}
            />
            {errors.sadrzaj && (
              <p className="text-sm text-destructive">{errors.sadrzaj.message}</p>
            )}
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={handleClose}>
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
      </div>
    </dialog>
  )
}
