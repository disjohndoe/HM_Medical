"use client"

import { useState, useCallback } from "react"
import { PlusIcon, ChevronLeftIcon, ChevronRightIcon, CalendarIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { PageHeader } from "@/components/shared/page-header"
import { CalendarView } from "@/components/appointments/calendar-view"
import { MonthView } from "@/components/appointments/month-view"
import { YearView } from "@/components/appointments/year-view"
import { AppointmentForm } from "@/components/appointments/appointment-form"
import { AppointmentDetail } from "@/components/appointments/appointment-detail"
import { useDoctors } from "@/lib/hooks/use-appointments"
import type { Appointment } from "@/lib/types"

type ViewMode = "day" | "week" | "month" | "year"

const VIEW_LABELS: Record<ViewMode, string> = {
  day: "Dan",
  week: "Tjedan",
  month: "Mjesec",
  year: "Godina",
}

export default function TerminiPage() {
  const [selectedDate, setSelectedDate] = useState(() => {
    const now = new Date()
    now.setHours(0, 0, 0, 0)
    return now
  })
  const [viewMode, setViewMode] = useState<ViewMode>("day")
  const [doktorId, setDoktorId] = useState<string>("")

  const [formOpen, setFormOpen] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [selectedAppointment, setSelectedAppointment] = useState<Appointment | null>(null)
  const [defaultSlotDate, setDefaultSlotDate] = useState<Date | undefined>()

  const { data: doctorsData } = useDoctors()
  const doctors = doctorsData ?? []

  const navigate = useCallback((direction: 1 | -1) => {
    setSelectedDate((prev) => {
      const next = new Date(prev)
      switch (viewMode) {
        case "day":
          next.setDate(next.getDate() + direction)
          break
        case "week":
          next.setDate(next.getDate() + direction * 7)
          break
        case "month":
          next.setMonth(next.getMonth() + direction)
          break
        case "year":
          next.setFullYear(next.getFullYear() + direction)
          break
      }
      return next
    })
  }, [viewMode])

  const goToToday = useCallback(() => {
    const now = new Date()
    now.setHours(0, 0, 0, 0)
    setSelectedDate(now)
  }, [])

  function handleSlotClick(date: Date) {
    setDefaultSlotDate(date)
    setSelectedAppointment(null)
    setFormOpen(true)
  }

  function handleAppointmentClick(apt: Appointment) {
    setSelectedAppointment(apt)
    setDetailOpen(true)
  }

  function handleEditAppointment(apt: Appointment) {
    setSelectedAppointment(apt)
    setDefaultSlotDate(new Date(apt.datum_vrijeme))
    setFormOpen(true)
  }

  function handleNewAppointment() {
    setDefaultSlotDate(selectedDate)
    setSelectedAppointment(null)
    setFormOpen(true)
  }

  function handleDayClick(date: Date) {
    setSelectedDate(date)
    setViewMode("day")
  }

  function handleMonthClick(date: Date) {
    setSelectedDate(date)
    setViewMode("month")
  }

  // Format header label based on view mode
  function getHeaderLabel(): string {
    switch (viewMode) {
      case "day":
        return selectedDate.toLocaleDateString("hr-HR", {
          weekday: "long",
          day: "numeric",
          month: "long",
          year: "numeric",
        })
      case "week": {
        const weekStart = new Date(selectedDate)
        const dayOfWeek = weekStart.getDay()
        const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
        weekStart.setDate(weekStart.getDate() + diff)
        const weekEnd = new Date(weekStart)
        weekEnd.setDate(weekEnd.getDate() + 6)
        const startStr = weekStart.toLocaleDateString("hr-HR", { day: "numeric", month: "short" })
        const endStr = weekEnd.toLocaleDateString("hr-HR", { day: "numeric", month: "short", year: "numeric" })
        return `${startStr} — ${endStr}`
      }
      case "month":
        return selectedDate.toLocaleDateString("hr-HR", { month: "long", year: "numeric" })
      case "year":
        return String(selectedDate.getFullYear()) + "."
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Termini" description="Kalendar termina">
        <Button onClick={handleNewAppointment}>
          <PlusIcon className="mr-2 h-4 w-4" />
          Novi termin
        </Button>
      </PageHeader>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => navigate(-1)}>
          <ChevronLeftIcon className="h-4 w-4" />
        </Button>
        <Button variant="outline" size="sm" onClick={goToToday}>
          <CalendarIcon className="mr-1 h-4 w-4" />
          Danas
        </Button>
        <Button variant="outline" size="sm" onClick={() => navigate(1)}>
          <ChevronRightIcon className="h-4 w-4" />
        </Button>

        <span className="text-sm font-medium ml-2">
          {getHeaderLabel()}
        </span>

        <div className="ml-auto flex items-center gap-2">
          {doctors.length > 1 && (
            <Select
              value={doktorId}
              onValueChange={(v) => setDoktorId(v ?? "")}
              items={[
                { value: "", label: "Svi doktori" },
                ...doctors.map((d) => ({
                  value: d.id,
                  label: `${d.prezime} ${d.ime}`,
                })),
              ]}
            >
              <SelectTrigger className="w-[200px]">
                <SelectValue placeholder="Svi doktori">
                  {(() => {
                    if (!doktorId) return undefined
                    const d = doctors.find((doc) => doc.id === doktorId)
                    return d ? `${d.prezime} ${d.ime}` : undefined
                  })()}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">Svi doktori</SelectItem>
                {doctors.map((d) => (
                  <SelectItem key={d.id} value={d.id}>
                    {d.prezime} {d.ime}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}

          <Select value={viewMode} onValueChange={(v) => setViewMode((v ?? "day") as ViewMode)}>
            <SelectTrigger className="w-[110px]">
              <SelectValue>{VIEW_LABELS[viewMode]}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="day">Dan</SelectItem>
              <SelectItem value="week">Tjedan</SelectItem>
              <SelectItem value="month">Mjesec</SelectItem>
              <SelectItem value="year">Godina</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Calendar Views */}
      {(viewMode === "day" || viewMode === "week") && (
        <CalendarView
          selectedDate={selectedDate}
          viewMode={viewMode}
          doktorId={doktorId || undefined}
          onSlotClick={handleSlotClick}
          onAppointmentClick={handleAppointmentClick}
        />
      )}

      {viewMode === "month" && (
        <MonthView
          selectedDate={selectedDate}
          doktorId={doktorId || undefined}
          onDayClick={handleDayClick}
          onAppointmentClick={handleAppointmentClick}
        />
      )}

      {viewMode === "year" && (
        <YearView
          selectedDate={selectedDate}
          doktorId={doktorId || undefined}
          onMonthClick={handleMonthClick}
        />
      )}

      {/* Dialogs */}
      <AppointmentForm
        open={formOpen}
        onOpenChange={setFormOpen}
        appointment={selectedAppointment ?? undefined}
        defaultDate={defaultSlotDate}
        defaultDoktorId={doktorId || undefined}
      />

      <AppointmentDetail
        appointment={selectedAppointment}
        open={detailOpen}
        onOpenChange={setDetailOpen}
        onEdit={handleEditAppointment}
        onUpdated={setSelectedAppointment}
      />
    </div>
  )
}
