"use client"

import { cn } from "@/lib/utils"
import { APPOINTMENT_VRSTA_COLORS, APPOINTMENT_VRSTA, WORKING_HOURS_START } from "@/lib/constants"
import type { Appointment } from "@/lib/types"

interface AppointmentCardProps {
  appointment: Appointment
  onClick: (appointment: Appointment) => void
}

export function AppointmentCard({ appointment, onClick }: AppointmentCardProps) {
  const start = new Date(appointment.datum_vrijeme)
  const startMin = start.getHours() * 60 + start.getMinutes()
  const topOffset = ((startMin - WORKING_HOURS_START * 60) / 60) * 64 // 64px per hour (4 rows * 16px)
  const height = (appointment.trajanje_minuta / 60) * 64

  const patientName = appointment.patient_ime && appointment.patient_prezime
    ? `${appointment.patient_ime} ${appointment.patient_prezime}`
    : "—"

  return (
    <div
      className={cn(
        "absolute left-1 right-1 z-10 rounded-md border px-2 py-1 text-xs cursor-pointer overflow-hidden transition-shadow hover:shadow-sm",
        APPOINTMENT_VRSTA_COLORS[appointment.vrsta] ?? "bg-gray-100 border-gray-300",
      )}
      style={{
        top: `${topOffset}px`,
        height: `${Math.max(height, 24)}px`,
      }}
      onClick={() => onClick(appointment)}
    >
      <div className="font-medium truncate">{patientName}</div>
      <div className="text-[10px] opacity-80 truncate">
        {String(start.getHours()).padStart(2, "0")}:{String(start.getMinutes()).padStart(2, "0")}
        {" — "}
        {APPOINTMENT_VRSTA[appointment.vrsta] ?? appointment.vrsta}
      </div>
    </div>
  )
}
