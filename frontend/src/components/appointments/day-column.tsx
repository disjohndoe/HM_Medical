"use client"

import { useMemo } from "react"
import { WORKING_HOURS_START, WORKING_HOURS_END, SLOT_GRANULARITY } from "@/lib/constants"
import type { Appointment } from "@/lib/types"
import { TimeSlot } from "./time-slot"
import { AppointmentCard } from "./appointment-card"

function computeOverlapLayout(appointments: Appointment[]): Map<string, { column: number; totalColumns: number }> {
  const result = new Map<string, { column: number; totalColumns: number }>()
  if (appointments.length === 0) return result

  const sorted = [...appointments].sort((a, b) => {
    const aStart = new Date(a.datum_vrijeme).getTime()
    const bStart = new Date(b.datum_vrijeme).getTime()
    if (aStart !== bStart) return aStart - bStart
    return b.trajanje_minuta - a.trajanje_minuta
  })

  const columns: { end: number }[] = []
  const eventCol = new Map<string, number>()

  for (const apt of sorted) {
    const start = new Date(apt.datum_vrijeme).getTime()
    const end = start + apt.trajanje_minuta * 60000
    let col = -1
    for (let i = 0; i < columns.length; i++) {
      if (start >= columns[i].end) {
        col = i
        columns[i].end = end
        break
      }
    }
    if (col === -1) {
      col = columns.length
      columns.push({ end })
    }
    eventCol.set(apt.id, col)
  }

  let clusterStart = 0
  let clusterEnd = new Date(sorted[0].datum_vrijeme).getTime() + sorted[0].trajanje_minuta * 60000
  let maxCol = eventCol.get(sorted[0].id)!

  for (let i = 1; i <= sorted.length; i++) {
    const start = i < sorted.length ? new Date(sorted[i].datum_vrijeme).getTime() : Infinity
    if (start >= clusterEnd) {
      const totalColumns = maxCol + 1
      for (let j = clusterStart; j < i; j++) {
        result.set(sorted[j].id, { column: eventCol.get(sorted[j].id)!, totalColumns })
      }
      if (i < sorted.length) {
        clusterStart = i
        clusterEnd = start + sorted[i].trajanje_minuta * 60000
        maxCol = eventCol.get(sorted[i].id)!
      }
    } else {
      clusterEnd = Math.max(clusterEnd, start + sorted[i].trajanje_minuta * 60000)
      maxCol = Math.max(maxCol, eventCol.get(sorted[i].id)!)
    }
  }

  return result
}

interface DayColumnProps {
  date: Date
  appointments: Appointment[]
  onSlotClick: (date: Date) => void
  onAppointmentClick: (appointment: Appointment) => void
  showDoctor?: boolean
}

export function DayColumn({ date, appointments, onSlotClick, onAppointmentClick, showDoctor }: DayColumnProps) {
  const hours: number[] = []
  for (let h = WORKING_HOURS_START; h < WORKING_HOURS_END; h++) {
    hours.push(h)
  }

  const slotsPerHour = 60 / SLOT_GRANULARITY
  const rowHeight = 16 // px per 15-min row

  const dayLabel = date.toLocaleDateString("hr-HR", {
    weekday: "short",
    day: "numeric",
    month: "numeric",
  })

  const overlapLayout = useMemo(() => computeOverlapLayout(appointments), [appointments])

  return (
    <div className="flex-1 min-w-0 border-l border-border">
      {/* Day header */}
      <div className="h-12 flex items-center justify-center text-xs font-medium text-muted-foreground border-b border-border">
        {dayLabel}
      </div>

      <div className="relative">
        {/* Hour labels + grid */}
        {hours.map((hour) => (
          <div key={hour} className="flex">
            {/* Hour label */}
            <div className="w-14 shrink-0 text-[10px] text-muted-foreground pr-2 pt-0 text-right">
              {String(hour).padStart(2, "0")}:00
            </div>
            {/* Rows */}
            <div className="flex-1 relative border-l border-border/50">
              {Array.from({ length: slotsPerHour }).map((_, i) => (
                <TimeSlot
                  key={`${hour}-${i}`}
                  hour={hour}
                  minute={i * SLOT_GRANULARITY}
                  onClick={(d) => {
                    const clicked = new Date(date)
                    clicked.setHours(d.getHours(), d.getMinutes(), 0, 0)
                    onSlotClick(clicked)
                  }}
                />
              ))}
            </div>
          </div>
        ))}

        {/* Appointment cards overlay */}
        <div
          className="absolute top-0 left-14 right-0"
          style={{ height: `${(WORKING_HOURS_END - WORKING_HOURS_START) * slotsPerHour * rowHeight}px` }}
        >
          {appointments.map((apt) => {
            const layout = overlapLayout.get(apt.id)
            return (
              <AppointmentCard
                key={apt.id}
                appointment={apt}
                onClick={onAppointmentClick}
                column={layout?.column ?? 0}
                totalColumns={layout?.totalColumns ?? 1}
                showDoctor={showDoctor}
              />
            )
          })}
        </div>
      </div>
    </div>
  )
}
