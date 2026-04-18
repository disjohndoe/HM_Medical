"use client"

import { useMemo } from "react"
import { useAppointments } from "@/lib/hooks/use-appointments"
import type { Appointment } from "@/lib/types"
import { DayColumn } from "./day-column"
import { LoadingSpinner } from "@/components/shared/loading-spinner"

interface CalendarViewProps {
  selectedDate: Date
  viewMode: "day" | "week"
  doktorId?: string
  onSlotClick: (date: Date) => void
  onAppointmentClick: (appointment: Appointment) => void
}

function formatDateKey(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, "0")
  const day = String(d.getDate()).padStart(2, "0")
  return `${y}-${m}-${day}`
}

export function CalendarView({
  selectedDate,
  viewMode,
  doktorId,
  onSlotClick,
  onAppointmentClick,
}: CalendarViewProps) {
  // Compute visible dates
  const dates = useMemo(() => {
    const result: Date[] = []
    if (viewMode === "day") {
      result.push(selectedDate)
    } else {
      const d = new Date(selectedDate)
      const dayOfWeek = d.getDay()
      const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
      d.setDate(d.getDate() + diff)
      for (let i = 0; i < 7; i++) {
        result.push(new Date(d))
        d.setDate(d.getDate() + 1)
      }
    }
    return result
  }, [selectedDate, viewMode])

  const dateFrom = formatDateKey(dates[0])
  const dateTo = formatDateKey(dates[dates.length - 1])

  const { data, isLoading } = useAppointments(
    dateFrom,
    dateTo,
    doktorId,
    undefined,
    0,
    200,
  )

  // Group appointments by day
  const groupedAppointments = useMemo(() => {
    const grouped: Record<string, Appointment[]> = {}
    for (const ds of dates) {
      grouped[formatDateKey(ds)] = []
    }
    if (data?.items) {
      for (const apt of data.items) {
        const key = formatDateKey(new Date(apt.datum_vrijeme))
        if (grouped[key]) {
          grouped[key].push(apt)
        }
      }
    }
    return grouped
  }, [data, dates])

  if (isLoading) {
    return <LoadingSpinner text="Učitavanje..." />
  }

  return (
    <div className="overflow-auto border rounded-lg bg-background">
      <div className="flex min-w-[600px]">
        {dates.map((d) => (
          <DayColumn
            key={formatDateKey(d)}
            date={d}
            appointments={groupedAppointments[formatDateKey(d)] ?? []}
            onSlotClick={onSlotClick}
            onAppointmentClick={onAppointmentClick}
            showDoctor={!doktorId}
          />
        ))}
      </div>
    </div>
  )
}
