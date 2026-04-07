"use client"

import { useState, useEffect, useRef, useMemo } from "react"
import { useForm, Controller } from "react-hook-form"
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
import {
  APPOINTMENT_VRSTA,
  APPOINTMENT_STATUS,
  DURATION_OPTIONS,
} from "@/lib/constants"
import {
  useCreateAppointment,
  useUpdateAppointment,
  useDoctors,
} from "@/lib/hooks/use-appointments"
import { usePatients } from "@/lib/hooks/use-patients"
import type { Appointment, AppointmentCreate } from "@/lib/types"

function formatLocalDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, "0")
  const day = String(d.getDate()).padStart(2, "0")
  return `${y}-${m}-${day}`
}

const appointmentSchema = z.object({
  patient_id: z.string().min(1, "Pacijent je obavezan"),
  doktor_id: z.string().min(1, "Doktor je obavezan"),
  datum: z.string().min(1, "Datum je obavezan"),
  vrijeme: z.string().min(1, "Vrijeme je obavezno"),
  trajanje_minuta: z.number().min(15).max(240),
  vrsta: z.string().min(1),
  napomena: z.string().optional(),
  status: z.string().optional(),
})

type AppointmentFormData = z.infer<typeof appointmentSchema>

interface AppointmentFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  appointment?: Appointment
  defaultDate?: Date
  defaultDoktorId?: string
}

export function AppointmentForm({
  open,
  onOpenChange,
  appointment,
  defaultDate,
  defaultDoktorId,
}: AppointmentFormProps) {
  const isEdit = !!appointment
  const createMutation = useCreateAppointment()
  const updateMutation = useUpdateAppointment()
  const { data: doctorsData } = useDoctors()
  const [patientSearch, setPatientSearch] = useState("")
  const [patientDropdownOpen, setPatientDropdownOpen] = useState(false)
  const { data: patientsData } = usePatients(patientSearch, 0, 20)
  const patientSearchRef = useRef<HTMLInputElement>(null)

  const doctors = useMemo(() => doctorsData ?? [], [doctorsData])

  const {
    register,
    handleSubmit,
    setValue,
    getValues,
    reset,
    control,
    formState: { errors },
  } = useForm<AppointmentFormData>({
    resolver: standardSchemaResolver(appointmentSchema),
  })

  useEffect(() => {
    if (open) {
      if (appointment) {
        const dt = new Date(appointment.datum_vrijeme)
        const dateStr = formatLocalDate(dt)
        const timeStr = `${String(dt.getHours()).padStart(2, "0")}:${String(dt.getMinutes()).padStart(2, "0")}`
        if (appointment.patient_prezime && appointment.patient_ime) {
          // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing local search state with appointment data
          setPatientSearch(`${appointment.patient_prezime} ${appointment.patient_ime}`)
        }
        reset({
          patient_id: appointment.patient_id,
          doktor_id: appointment.doktor_id,
          datum: dateStr,
          vrijeme: timeStr,
          trajanje_minuta: appointment.trajanje_minuta,
          vrsta: appointment.vrsta,
          napomena: appointment.napomena ?? undefined,
          status: appointment.status,
        })
      } else {
        setPatientSearch("")
        const dateStr = defaultDate ? formatLocalDate(defaultDate) : ""
        const timeStr = defaultDate
          ? `${String(defaultDate.getHours()).padStart(2, "0")}:${String(defaultDate.getMinutes()).padStart(2, "0")}`
          : ""
        reset({
          patient_id: "",
          doktor_id: "",
          datum: dateStr,
          vrijeme: timeStr,
          trajanje_minuta: 30,
          vrsta: "pregled",
          napomena: undefined,
          status: undefined,
        })
      }
    }
  }, [open, appointment, defaultDate, reset])

  // Auto-select doctor when there's only one, or use the default
  useEffect(() => {
    if (!open) return
    const currentDoktorId = getValues("doktor_id")
    if (currentDoktorId && doctors.some((d) => d.id === currentDoktorId)) return
    if (defaultDoktorId && doctors.some((d) => d.id === defaultDoktorId)) {
      setValue("doktor_id", defaultDoktorId)
    } else if (doctors.length === 1) {
      setValue("doktor_id", doctors[0].id)
    }
  }, [open, doctors, defaultDoktorId, setValue, getValues])

  async function onSubmit(data: AppointmentFormData) {
    try {
      const datum_vrijeme = new Date(`${data.datum}T${data.vrijeme}:00`).toISOString()

      if (isEdit && appointment) {
        const payload: Record<string, unknown> = {
          patient_id: data.patient_id,
          doktor_id: data.doktor_id,
          datum_vrijeme,
          trajanje_minuta: data.trajanje_minuta,
          vrsta: data.vrsta,
          napomena: data.napomena ?? undefined,
        }
        if (data.status) payload.status = data.status
        await updateMutation.mutateAsync({ id: appointment.id, data: payload })
        toast.success("Termin ažuriran")
      } else {
        const payload: AppointmentCreate = {
          patient_id: data.patient_id,
          doktor_id: data.doktor_id,
          datum_vrijeme,
          trajanje_minuta: data.trajanje_minuta,
          vrsta: data.vrsta,
          napomena: data.napomena ?? undefined,
        }
        await createMutation.mutateAsync(payload)
        toast.success("Termin kreiran")
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
          <DialogTitle>{isEdit ? "Uredi termin" : "Novi termin"}</DialogTitle>
          <DialogDescription>
            {isEdit ? "Promijenite podatke o terminu" : "Zakazite novi termin za pacijenta"}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* Pacijent */}
          <div className="space-y-2">
            <Label>Pacijent *</Label>
            <div className="relative">
              <Input
                ref={patientSearchRef}
                placeholder="Pretraži pacijente (ime, prezime, OIB...)"
                value={patientSearch}
                onChange={(e) => {
                  setPatientSearch(e.target.value)
                  setPatientDropdownOpen(true)
                  if (e.target.value === "") {
                    setValue("patient_id", "")
                  }
                }}
                onFocus={() => setPatientDropdownOpen(true)}
              onBlur={() => setTimeout(() => setPatientDropdownOpen(false), 200)}
              />
              {patientDropdownOpen && patientSearch.length > 0 && (patientsData?.items ?? []).length > 0 && (
                <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-md max-h-48 overflow-y-auto">
                  {(patientsData?.items ?? []).map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      className="flex w-full items-center px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground cursor-pointer"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => {
                        setValue("patient_id", p.id)
                        setPatientSearch(`${p.prezime} ${p.ime}`)
                        setPatientDropdownOpen(false)
                      }}
                    >
                      {p.prezime} {p.ime} {p.oib ? `(${p.oib})` : ""}
                    </button>
                  ))}
                </div>
              )}
              {patientDropdownOpen && patientSearch.length > 0 && (patientsData?.items ?? []).length === 0 && (
                <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover shadow-md">
                  <div className="px-3 py-2 text-sm text-muted-foreground">Nema rezultata</div>
                </div>
              )}
            </div>
            {errors.patient_id && (
              <p className="text-sm text-destructive">{errors.patient_id.message}</p>
            )}
          </div>

          {/* Doktor */}
          <div className="space-y-2">
            <Label>Doktor *</Label>
            <Controller
              name="doktor_id"
              control={control}
              render={({ field }) => (
                <Select
                  value={field.value ?? ""}
                  onValueChange={field.onChange}
                  disabled={doctors.length <= 1}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Odaberite doktora">
                      {(() => {
                        const id = field.value
                        if (!id) return undefined
                        const d = doctors.find((doc) => doc.id === id)
                        if (d) return `${d.titula ? `${d.titula} ` : ""}${d.prezime} ${d.ime}`
                        // Fallback: use denormalized name from appointment (e.g. deactivated doctor)
                        if (appointment?.doktor_id === id && appointment.doktor_prezime)
                          return `${appointment.doktor_prezime} ${appointment.doktor_ime ?? ""}`.trim()
                        return "Učitavanje..."
                      })()}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {doctors.map((d) => (
                      <SelectItem key={d.id} value={d.id}>
                        {d.titula ? `${d.titula} ` : ""}{d.prezime} {d.ime}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
            {errors.doktor_id && (
              <p className="text-sm text-destructive">{errors.doktor_id.message}</p>
            )}
          </div>

          {/* Datum i vrijeme */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="datum">Datum *</Label>
              <Input id="datum" type="date" lang="hr" {...register("datum")} />
              {errors.datum && (
                <p className="text-sm text-destructive">{errors.datum.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="vrijeme">Vrijeme *</Label>
              <Input id="vrijeme" type="time" {...register("vrijeme")} />
              {errors.vrijeme && (
                <p className="text-sm text-destructive">{errors.vrijeme.message}</p>
              )}
            </div>
          </div>

          {/* Trajanje i vrsta */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Trajanje</Label>
              <Controller
                name="trajanje_minuta"
                control={control}
                render={({ field }) => (
                  <Select
                    value={String(field.value ?? 30)}
                    onValueChange={(v) => field.onChange(Number(v ?? 30))}
                  >
                    <SelectTrigger>
                      <SelectValue>
                        {(() => {
                          const m = field.value ?? 30
                          if (m >= 60 && m % 60 === 0) return `${m / 60} h`
                          if (m >= 60) return `${Math.floor(m / 60)} h ${m % 60} min`
                          return `${m} min`
                        })()}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {DURATION_OPTIONS.map((d) => (
                        <SelectItem key={d} value={String(d)}>
                          {d >= 60 && d % 60 === 0 ? `${d / 60} h` : d >= 60 ? `${Math.floor(d / 60)} h ${d % 60} min` : `${d} min`}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
            <div className="space-y-2">
              <Label>Vrsta</Label>
              <Controller
                name="vrsta"
                control={control}
                render={({ field }) => (
                  <Select
                    value={field.value ?? "pregled"}
                    onValueChange={field.onChange}
                  >
                    <SelectTrigger>
                      <SelectValue>
                        {APPOINTMENT_VRSTA[field.value ?? "pregled"] ?? field.value}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(APPOINTMENT_VRSTA).map(([key, label]) => (
                        <SelectItem key={key} value={key}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
          </div>

          {/* Status (edit only) */}
          {isEdit && (
            <div className="space-y-2">
              <Label>Status</Label>
              <Controller
                name="status"
                control={control}
                render={({ field }) => (
                  <Select
                    value={field.value ?? appointment?.status}
                    onValueChange={(v) => field.onChange(v ?? undefined)}
                  >
                    <SelectTrigger>
                      <SelectValue>
                        {APPOINTMENT_STATUS[(field.value ?? appointment?.status) as keyof typeof APPOINTMENT_STATUS]}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(APPOINTMENT_STATUS).map(([key, label]) => (
                        <SelectItem key={key} value={key}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
          )}

          {/* Napomena */}
          <div className="space-y-2">
            <Label htmlFor="napomena">Napomena</Label>
            <Textarea
              id="napomena"
              placeholder="Dodatne napomene..."
              {...register("napomena")}
            />
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
                  : "Zakaži"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
