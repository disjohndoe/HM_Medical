"use client"
/* eslint-disable react-hooks/incompatible-library -- react-hook-form watch() is intentionally used */

import { useRouter } from "next/navigation"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { standardSchemaResolver } from "@hookform/resolvers/standard-schema"
import { toast } from "sonner"
import { SaveIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { SPOL_OPTIONS } from "@/lib/constants"
import type { Patient } from "@/lib/types"

const patientSchema = z.object({
  ime: z.string().min(1, "Ime je obavezno"),
  prezime: z.string().min(1, "Prezime je obavezno"),
  datum_rodjenja: z.string().nullable().optional(),
  spol: z.string().nullable().optional(),
  oib: z
    .string()
    .nullable()
    .optional()
    .refine(
      (v) => !v || /^\d{11}$/.test(v),
      "OIB mora imati točno 11 znamenki"
    ),
  mbo: z
    .string()
    .nullable()
    .optional()
    .refine(
      (v) => !v || /^\d{9}$/.test(v),
      "MBO mora imati točno 9 znamenki"
    ),
  adresa: z.string().nullable().optional(),
  grad: z.string().nullable().optional(),
  postanski_broj: z.string().nullable().optional(),
  telefon: z.string().nullable().optional(),
  mobitel: z.string().nullable().optional(),
  email: z
    .string()
    .email("Neispravna email adresa")
    .nullable()
    .optional()
    .or(z.literal("")),
  napomena: z.string().nullable().optional(),
  alergije: z.string().nullable().optional(),
})

type PatientFormData = z.infer<typeof patientSchema>

interface PatientFormProps {
  patient?: Patient
  onSubmit: (data: PatientFormData) => Promise<void>
  isSubmitting?: boolean
}

export function PatientForm({ patient, onSubmit, isSubmitting }: PatientFormProps) {
  const router = useRouter()
  const isEdit = !!patient

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<PatientFormData>({
    resolver: standardSchemaResolver(patientSchema),
    defaultValues: patient
      ? {
          ime: patient.ime,
          prezime: patient.prezime,
          datum_rodjenja: patient.datum_rodjenja?.split("T")[0] ?? null,
          spol: patient.spol ?? null,
          oib: patient.oib ?? null,
          mbo: patient.mbo ?? null,
          adresa: patient.adresa ?? null,
          grad: patient.grad ?? null,
          postanski_broj: patient.postanski_broj ?? null,
          telefon: patient.telefon ?? null,
          mobitel: patient.mobitel ?? null,
          email: patient.email ?? null,
          napomena: patient.napomena ?? null,
          alergije: patient.alergije ?? null,
        }
      : {
          ime: "",
          prezime: "",
          datum_rodjenja: null,
          spol: null,
          oib: null,
          mbo: null,
          adresa: null,
          grad: null,
          postanski_broj: null,
          telefon: null,
          mobitel: null,
          email: null,
          napomena: null,
          alergije: null,
        },
  })

  const spolValue = watch("spol")

  async function handleFormSubmit(data: PatientFormData) {
    try {
      await onSubmit({
        ...data,
        email: data.email || null,
        oib: data.oib || null,
        mbo: data.mbo || null,
      })
      toast.success(isEdit ? "Pacijent ažuriran" : "Pacijent kreiran")
      if (!isEdit) {
        router.push("/pacijenti")
      } else {
        router.push(`/pacijenti/${patient.id}`)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Greška pri spremanju")
    }
  }

  return (
    <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-6">
      {/* Osobni podaci */}
      <Card>
        <CardHeader>
          <CardTitle>Osobni podaci</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="ime">Ime *</Label>
            <Input id="ime" {...register("ime")} />
            {errors.ime && (
              <p className="text-sm text-destructive">{errors.ime.message}</p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="prezime">Prezime *</Label>
            <Input id="prezime" {...register("prezime")} />
            {errors.prezime && (
              <p className="text-sm text-destructive">{errors.prezime.message}</p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="datum_rodjenja">Datum rođenja</Label>
            <Input
              id="datum_rodjenja"
              type="date"
              {...register("datum_rodjenja")}
            />
          </div>
          <div className="space-y-2">
            <Label>Spol</Label>
            <Select
              value={spolValue ?? ""}
              onValueChange={(v) => setValue("spol", v || null)}
            >
              <SelectTrigger>
                <SelectValue placeholder="Odaberite spol">
                  {SPOL_OPTIONS.find((o) => o.value === spolValue)?.label}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {SPOL_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="oib">OIB</Label>
            <Input
              id="oib"
              maxLength={11}
              placeholder="11 znamenki"
              {...register("oib")}
            />
            {errors.oib && (
              <p className="text-sm text-destructive">{errors.oib.message}</p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="mbo">MBO</Label>
            <Input
              id="mbo"
              maxLength={9}
              placeholder="9 znamenki"
              {...register("mbo")}
            />
            {errors.mbo && (
              <p className="text-sm text-destructive">{errors.mbo.message}</p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Kontakt podaci */}
      <Card>
        <CardHeader>
          <CardTitle>Kontakt podaci</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="adresa">Adresa</Label>
            <Input id="adresa" {...register("adresa")} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="grad">Grad</Label>
            <Input id="grad" {...register("grad")} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="postanski_broj">Poštanski broj</Label>
            <Input id="postanski_broj" {...register("postanski_broj")} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="telefon">Telefon</Label>
            <Input id="telefon" {...register("telefon")} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="mobitel">Mobitel</Label>
            <Input id="mobitel" {...register("mobitel")} />
          </div>
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" {...register("email")} />
            {errors.email && (
              <p className="text-sm text-destructive">{errors.email.message}</p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Medicinski podaci */}
      <Card>
        <CardHeader>
          <CardTitle>Medicinski podaci</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="alergije">Alergije</Label>
            <Textarea
              id="alergije"
              placeholder="Npr. penicilin, ibuprofen..."
              {...register("alergije")}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="napomena">Napomena</Label>
            <Textarea
              id="napomena"
              placeholder="Dodatne napomene o pacijentu..."
              {...register("napomena")}
            />
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center justify-end gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={() => router.back()}
        >
          Odustani
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          <SaveIcon className="mr-2 h-4 w-4" />
          {isSubmitting
            ? "Spremanje..."
            : isEdit
              ? "Ažuriraj pacijenta"
              : "Kreiraj pacijenta"}
        </Button>
      </div>
    </form>
  )
}
