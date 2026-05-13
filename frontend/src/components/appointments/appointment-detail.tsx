"use client"

import { useState } from "react"
import { toast } from "sonner"
import { PlusIcon, XIcon } from "lucide-react"
import { formatDateTimeHR, formatCurrencyEUR } from "@/lib/utils"
import { APPOINTMENT_STATUS, APPOINTMENT_VRSTA, APPOINTMENT_STATUS_COLORS } from "@/lib/constants"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { Badge } from "@/components/ui/badge"
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
import { useUpdateAppointment } from "@/lib/hooks/use-appointments"
import { useProcedures, useCreatePerformed } from "@/lib/hooks/use-procedures"
import type { Appointment } from "@/lib/types"

interface AppointmentDetailProps {
  appointment: Appointment | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onEdit: (appointment: Appointment) => void
  onUpdated?: (appointment: Appointment) => void
}

const QUICK_STATUS_ACTIONS: Record<string, { label: string; status: string }> = {
  zakazan: { label: "Potvrdi", status: "potvrdjen" },
  potvrdjen: { label: "Započni", status: "u_tijeku" },
  u_tijeku: { label: "Završi", status: "zavrsen" },
}

interface ProcedureRow {
  procedure_id: string
  cijena_eur: string
  napomena: string
}

function emptyRow(): ProcedureRow {
  return { procedure_id: "", cijena_eur: "", napomena: "" }
}

export function AppointmentDetail({ appointment, open, onOpenChange, onEdit, onUpdated }: AppointmentDetailProps) {
  const updateMutation = useUpdateAppointment()
  const createPerformed = useCreatePerformed()
  const { data: proceduresData } = useProcedures(undefined, 0, 100)
  const [showProcedurePrompt, setShowProcedurePrompt] = useState(false)
  const [showProcedureForm, setShowProcedureForm] = useState(false)
  const [rows, setRows] = useState<ProcedureRow[]>([emptyRow()])
  const [saving, setSaving] = useState(false)

  const procedures = proceduresData?.items ?? []

  if (!appointment) return null

  const patientName = appointment.patient_ime && appointment.patient_prezime
    ? `${appointment.patient_ime} ${appointment.patient_prezime}`
    : "—"

  const doktorName = appointment.doktor_ime && appointment.doktor_prezime
    ? `${appointment.doktor_ime} ${appointment.doktor_prezime}`
    : "—"

  const appointmentId = appointment.id

  function resetProcedureState() {
    setShowProcedurePrompt(false)
    setShowProcedureForm(false)
    setRows([emptyRow()])
  }

  function handleDialogChange(isOpen: boolean) {
    if (!isOpen) resetProcedureState()
    onOpenChange(isOpen)
  }

  async function handleStatusChange(newStatus: string) {
    try {
      const updated = await updateMutation.mutateAsync({ id: appointmentId, data: { status: newStatus } })
      toast.success(`Status promijenjen: ${APPOINTMENT_STATUS[newStatus]}`)
      onUpdated?.(updated)
      if (newStatus === "zavrsen") {
        setShowProcedurePrompt(true)
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Greška pri promjeni statusa")
    }
  }

  async function handleCancel() {
    try {
      const updated = await updateMutation.mutateAsync({ id: appointmentId, data: { status: "otkazan" } })
      toast.success("Termin otkazan")
      onUpdated?.(updated)
      handleDialogChange(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Greška pri otkazivanju")
    }
  }

  function updateRow(index: number, field: keyof ProcedureRow, value: string) {
    setRows(prev => prev.map((r, i) => i === index ? { ...r, [field]: value } : r))
  }

  function removeRow(index: number) {
    setRows(prev => prev.length === 1 ? [emptyRow()] : prev.filter((_, i) => i !== index))
  }

  async function handleSaveProcedures() {
    const validRows = rows.filter(r => r.procedure_id)
    if (validRows.length === 0) {
      handleDialogChange(false)
      return
    }

    setSaving(true)
    try {
      if (!appointment) return
      const datum = appointment.datum_vrijeme.split("T")[0]
      for (const row of validRows) {
        const cijenaCents = row.cijena_eur ? Math.round(parseFloat(row.cijena_eur) * 100) : undefined
        await createPerformed.mutateAsync({
          patient_id: appointment.patient_id,
          procedure_id: row.procedure_id,
          appointment_id: appointmentId,
          datum,
          cijena_cents: cijenaCents,
          napomena: row.napomena || undefined,
        })
      }
      toast.success(`${validRows.length} postupak/a zabilježen/o`)
      handleDialogChange(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Greška pri spremanju postupaka")
    } finally {
      setSaving(false)
    }
  }

  const quickAction = QUICK_STATUS_ACTIONS[appointment.status]

  // Procedure prompt after finishing
  if (showProcedurePrompt && !showProcedureForm) {
    return (
      <Dialog open={open} onOpenChange={handleDialogChange}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Termin završen</DialogTitle>
            <DialogDescription>
              {patientName} — {APPOINTMENT_VRSTA[appointment.vrsta] ?? appointment.vrsta}
            </DialogDescription>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Želite li dodati izvršene postupke za ovaj termin?
          </p>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => handleDialogChange(false)}>
              Preskoči
            </Button>
            <Button onClick={() => setShowProcedureForm(true)}>
              <PlusIcon className="mr-2 h-4 w-4" />
              Dodaj postupke
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    )
  }

  // Procedure form
  if (showProcedureForm) {
    return (
      <Dialog open={open} onOpenChange={handleDialogChange}>
        <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Postupci za termin</DialogTitle>
            <DialogDescription>
              {patientName} — {formatDateTimeHR(appointment.datum_vrijeme)}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {rows.map((row, index) => (
              <div key={index} className="space-y-3 rounded-lg border p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">Postupak {index + 1}</span>
                  {rows.length > 1 && (
                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => removeRow(index)}>
                      <XIcon className="h-4 w-4" />
                    </Button>
                  )}
                </div>
                <div className="space-y-2">
                  <Label>Postupak *</Label>
                  <Select value={row.procedure_id ?? ""} onValueChange={(v) => v && updateRow(index, "procedure_id", v)}>
                    <SelectTrigger>
                      <SelectValue placeholder="Odaberite postupak">
                        {row.procedure_id
                          ? (() => { const p = procedures.find(x => x.id === row.procedure_id); return p ? `[${p.sifra}] ${p.naziv}` : undefined })()
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
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <Label>Cijena (EUR)</Label>
                    <Input
                      type="number"
                      step="0.01"
                      min="0"
                      placeholder={
                        row.procedure_id
                          ? String((procedures.find(p => p.id === row.procedure_id)?.cijena_cents ?? 0) / 100)
                          : "Prema katalogu"
                      }
                      value={row.cijena_eur}
                      onChange={(e) => updateRow(index, "cijena_eur", e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Napomena</Label>
                    <Textarea
                      className="min-h-[60px]"
                      placeholder="..."
                      value={row.napomena}
                      onChange={(e) => updateRow(index, "napomena", e.target.value)}
                    />
                  </div>
                </div>
              </div>
            ))}

            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() => setRows(prev => [...prev, emptyRow()])}
            >
              <PlusIcon className="mr-2 h-4 w-4" />
              Dodaj još
            </Button>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => handleDialogChange(false)}>
                Odustani
              </Button>
              <Button onClick={handleSaveProcedures} disabled={saving}>
                {saving ? "Spremanje..." : "Spremi i zatvori"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    )
  }

  // Default: appointment detail view
  return (
    <Dialog open={open} onOpenChange={handleDialogChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Detalji termina</DialogTitle>
          <DialogDescription>
            {APPOINTMENT_VRSTA[appointment.vrsta] ?? appointment.vrsta}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Status */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Status</span>
            <Badge className={APPOINTMENT_STATUS_COLORS[appointment.status] ?? ""}>
              {APPOINTMENT_STATUS[appointment.status] ?? appointment.status}
            </Badge>
          </div>

          {/* Pacijent */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Pacijent</span>
            <span className="text-sm font-medium">{patientName}</span>
          </div>

          {/* Doktor */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Doktor</span>
            <span className="text-sm font-medium">{doktorName}</span>
          </div>

          {/* Datum */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Datum</span>
            <span className="text-sm font-medium">{formatDateTimeHR(appointment.datum_vrijeme)}</span>
          </div>

          {/* Trajanje */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Trajanje</span>
            <span className="text-sm font-medium">{appointment.trajanje_minuta} min</span>
          </div>

          {/* Napomena */}
          {appointment.napomena && (
            <div className="space-y-1">
              <span className="text-sm text-muted-foreground">Napomena</span>
              <p className="text-sm bg-muted rounded-md p-2">{appointment.napomena}</p>
            </div>
          )}

          {/* Actions */}
          <div className="flex flex-wrap gap-2 pt-2">
            {quickAction && quickAction.status !== "zavrsen" && (
              <Button
                size="sm"
                onClick={() => handleStatusChange(quickAction.status)}
                disabled={updateMutation.isPending}
              >
                {quickAction.label}
              </Button>
            )}
            {appointment.status !== "zavrsen" && appointment.status !== "otkazan" && appointment.status !== "nije_dosao" && (
              <Button
                size="sm"
                variant="default"
                onClick={() => handleStatusChange("zavrsen")}
                disabled={updateMutation.isPending}
              >
                Završi
              </Button>
            )}
            {appointment.status === "zakazan" || appointment.status === "potvrdjen" ? (
              <Button size="sm" variant="destructive" onClick={handleCancel} disabled={updateMutation.isPending}>
                Otkaži
              </Button>
            ) : null}
            {(appointment.status === "zakazan" || appointment.status === "potvrdjen") && (
              <Button size="sm" variant="outline" onClick={() => { handleDialogChange(false); onEdit(appointment) }}>
                Uredi
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
