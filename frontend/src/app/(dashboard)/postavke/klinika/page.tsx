"use client"

import { useEffect, useState } from "react"
import { useForm, Controller } from "react-hook-form"
import { standardSchemaResolver } from "@hookform/resolvers/standard-schema"
import { z } from "zod"
import { Save, Loader2, KeyRound } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { PageHeader } from "@/components/shared/page-header"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { useClinicSettings, useUpdateClinicSettings, usePlanUsage, useGenerateOid } from "@/lib/hooks/use-settings"
import { TENANT_VRSTA_OPTIONS, PLAN_TIER, CEZIH_STATUS, CEZIH_STATUS_COLORS } from "@/lib/constants"

const nullableString = z
  .string()
  .nullable()
  .optional()
  .transform((v) => (v === "" ? null : v))

const clinicSchema = z.object({
  naziv: z.string().min(1, "Naziv je obavezan"),
  vrsta: z.string().min(1, "Vrsta je obavezna"),
  email: z.string().email("Neispravan email"),
  telefon: nullableString,
  adresa: nullableString,
  oib: z
    .string()
    .length(11, "OIB mora imati 11 znakova")
    .nullable()
    .optional()
    .transform((v) => (v === "" ? null : v)),
  grad: nullableString,
  postanski_broj: nullableString,
  zupanija: nullableString,
  web: nullableString,
  sifra_ustanove: nullableString,
  has_hzzo_contract: z.boolean().optional(),
})

type ClinicFormData = z.infer<typeof clinicSchema>

function formatTrialRemaining(days: number): string {
  if (days >= 1) {
    const d = Math.floor(days)
    return `${d} ${d === 1 ? "dan" : "dana"}`
  }
  const hours = Math.ceil(days * 24)
  return `${hours} ${hours === 1 ? "sat" : hours < 5 ? "sata" : "sati"}`
}

export default function KlinikaSettingsPage() {
  const { data: clinic, isLoading } = useClinicSettings()
  const updateClinic = useUpdateClinicSettings()
  const generateOid = useGenerateOid()
  const [showOidConfirm, setShowOidConfirm] = useState(false)
  const { data: usage } = usePlanUsage()

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<ClinicFormData>({
    resolver: standardSchemaResolver(clinicSchema),
  })

  useEffect(() => {
    if (clinic) {
      reset({
        naziv: clinic.naziv ?? "",
        vrsta: clinic.vrsta ?? "ordinacija",
        email: clinic.email ?? "",
        telefon: clinic.telefon ?? null,
        adresa: clinic.adresa ?? null,
        oib: clinic.oib ?? null,
        grad: clinic.grad ?? null,
        postanski_broj: clinic.postanski_broj ?? null,
        zupanija: clinic.zupanija ?? null,
        web: clinic.web ?? null,
        sifra_ustanove: clinic.sifra_ustanove ?? null,
        has_hzzo_contract: clinic.has_hzzo_contract ?? false,
      })
    }
  }, [clinic, reset])

  const onSubmit = (data: ClinicFormData) => {
    updateClinic.mutate(data, {
      onSuccess: () => toast.success("Postavke klinike spremljene"),
    })
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader title="Postavke klinike" />
        <LoadingSpinner text="Učitavanje..." />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Postavke klinike" />

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Osnovni podaci</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="naziv">Naziv klinike</Label>
                <Input id="naziv" {...register("naziv")} />
                {errors.naziv && (
                  <p className="text-xs text-destructive">{errors.naziv.message}</p>
                )}
              </div>
              <div className="space-y-2">
                <Label>Vrsta</Label>
                <Controller
                  name="vrsta"
                  control={control}
                  render={({ field }) => (
                    <Select value={field.value ?? "ordinacija"} onValueChange={field.onChange}>
                      <SelectTrigger>
                        <SelectValue>
                          {TENANT_VRSTA_OPTIONS.find((o) => o.value === (field.value ?? "ordinacija"))?.label}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {TENANT_VRSTA_OPTIONS.map((opt) => (
                          <SelectItem key={opt.value} value={opt.value}>
                            {opt.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" {...register("email")} />
                {errors.email && (
                  <p className="text-xs text-destructive">{errors.email.message}</p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="telefon">Telefon</Label>
                <Input id="telefon" {...register("telefon")} />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="adresa">Adresa</Label>
              <Input id="adresa" {...register("adresa")} />
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="grad">Grad</Label>
                <Input id="grad" {...register("grad")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="postanski_broj">Poštanski broj</Label>
                <Input id="postanski_broj" {...register("postanski_broj")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="zupanija">Županija</Label>
                <Input id="zupanija" {...register("zupanija")} />
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="oib">OIB</Label>
                <Input id="oib" maxLength={11} {...register("oib")} />
                {errors.oib && (
                  <p className="text-xs text-destructive">{errors.oib.message}</p>
                )}
              </div>
              <div className="space-y-2">
                <Label htmlFor="web">Web stranica</Label>
                <Input id="web" placeholder="https://..." {...register("web")} />
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <Button type="submit" disabled={updateClinic.isPending}>
                {updateClinic.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                <Save className="mr-2 h-4 w-4" />
                Spremi
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>CEZIH integracija</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">Status:</span>
              <span
                className={`inline-block h-2 w-2 rounded-full ${CEZIH_STATUS_COLORS[clinic?.cezih_status ?? "nepovezano"]}`}
              />
              <span className="text-sm">
                {CEZIH_STATUS[clinic?.cezih_status ?? "nepovezano"]}
              </span>
            </div>

            <Separator />

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="sifra_ustanove">Šifra ustanove</Label>
                <Input
                  id="sifra_ustanove"
                  placeholder="npr. 12345"
                  {...register("sifra_ustanove")}
                />
                <p className="text-xs text-muted-foreground">
                  Dobijete od HZZO-a pri registraciji zdravstvene ustanove
                </p>
              </div>
              <div className="space-y-2">
                <Label>OID informacijskog sustava</Label>
                {clinic?.oid ? (
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm select-all bg-muted px-3 py-2 rounded-md">
                      {clinic.oid}
                    </span>
                    <span className="inline-flex items-center rounded-md bg-green-50 px-2 py-1 text-xs font-medium text-green-700 ring-1 ring-green-600/20 ring-inset">
                      Automatski generirano
                    </span>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <p className="text-sm text-muted-foreground">
                      OID nije generiran. Potreban je za slanje dokumenata u CEZIH.
                    </p>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setShowOidConfirm(true)}
                      disabled={generateOid.isPending}
                    >
                      {generateOid.isPending ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <KeyRound className="mr-2 h-4 w-4" />
                      )}
                      Generiraj OID
                    </Button>
                  </div>
                )}
              </div>
            </div>

            <Separator />

            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="has_hzzo_contract"
                className="h-4 w-4 rounded border-gray-300"
                {...register("has_hzzo_contract")}
              />
              <div>
                <Label htmlFor="has_hzzo_contract" className="cursor-pointer">
                  Ugovor s HZZO-om
                </Label>
                <p className="text-xs text-muted-foreground">
                  Omogućuje slanje e-Recepata i e-Uputnica putem CEZIH-a
                </p>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <Button type="submit" disabled={updateClinic.isPending}>
                {updateClinic.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                <Save className="mr-2 h-4 w-4" />
                Spremi CEZIH podatke
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle> Pretplata</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <p className="text-sm text-muted-foreground">Plan</p>
                <p className="text-lg font-semibold">
                  {PLAN_TIER[clinic?.plan_tier ?? "trial"] ?? clinic?.plan_tier}
                </p>
              </div>
              {usage?.trial_days_remaining != null && (
                <div>
                  <p className="text-sm text-muted-foreground">Trial ističe</p>
                  <p className={`text-lg font-semibold ${usage.trial_days_remaining <= 3 ? "text-destructive" : ""}`}>
                    {formatTrialRemaining(usage.trial_days_remaining)}
                  </p>
                </div>
              )}
            </div>

            {usage && (
              <div className="space-y-3 pt-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Korisnici</span>
                  <span className="font-medium">
                    {usage.users.current} / {usage.users.max}
                  </span>
                </div>
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${usage.users.current >= usage.users.max ? "bg-destructive" : "bg-primary"}`}
                    style={{ width: `${Math.min(100, (usage.users.current / usage.users.max) * 100)}%` }}
                  />
                </div>

                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Pacijenti</span>
                  <span className="font-medium">
                    {usage.patients.current} / {usage.patients.max ?? "∞"}
                  </span>
                </div>
                {usage.patients.max != null && (
                  <div className="h-2 rounded-full bg-muted overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${usage.patients.current >= usage.patients.max ? "bg-destructive" : "bg-primary"}`}
                      style={{ width: `${Math.min(100, (usage.patients.current / usage.patients.max) * 100)}%` }}
                    />
                  </div>
                )}

                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Aktivne sesije Vašeg tima</span>
                  <span className="font-medium">
                    {usage.sessions.current} / {usage.sessions.max}
                  </span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </form>

      <ConfirmDialog
        open={showOidConfirm}
        onOpenChange={setShowOidConfirm}
        title="Generiranje OID-a"
        description="Ovo šalje zahtjev u CEZIH i ne može se poništiti. OID se nakon generiranja neće moći promijeniti."
        confirmLabel="Generiraj OID"
        onConfirm={() => {
          setShowOidConfirm(false)
          generateOid.mutate()
        }}
        loading={generateOid.isPending}
      />
    </div>
  )
}
