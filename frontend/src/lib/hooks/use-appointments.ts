import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/api-client"
import type { Appointment, AppointmentCreate, AvailableSlot, PaginatedResponse, User } from "@/lib/types"

export function useDoctors() {
  return useQuery({
    queryKey: ["users", "doctors"],
    queryFn: () => api.get<PaginatedResponse<User>>("/users/doctors?limit=100"),
    select: (data) => data.items,
  })
}

export function useAppointments(
  dateFrom?: string,
  dateTo?: string,
  doktorId?: string,
  statusFilter?: string,
  skip = 0,
  limit = 50,
) {
  const params = new URLSearchParams()
  if (dateFrom) params.set("date_from", dateFrom)
  if (dateTo) params.set("date_to", dateTo)
  if (doktorId) params.set("doktor_id", doktorId)
  if (statusFilter) params.set("status", statusFilter)
  params.set("skip", String(skip))
  params.set("limit", String(limit))

  return useQuery({
    queryKey: ["appointments", dateFrom, dateTo, doktorId, statusFilter, skip, limit],
    queryFn: () =>
      api.get<PaginatedResponse<Appointment>>(`/appointments?${params.toString()}`),
  })
}

export function useDayAppointments(day: string, doktorId?: string) {
  const params = new URLSearchParams()
  if (doktorId) params.set("doktor_id", doktorId)

  return useQuery({
    queryKey: ["appointments", "day", day, doktorId],
    queryFn: () =>
      api.get<Appointment[]>(`/appointments/day/${day}?${params.toString()}`),
    enabled: !!day,
  })
}

export function useAppointment(id: string) {
  return useQuery({
    queryKey: ["appointments", id],
    queryFn: () => api.get<Appointment>(`/appointments/${id}`),
    enabled: !!id,
  })
}

export function useCreateAppointment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: AppointmentCreate) =>
      api.post<Appointment>("/appointments", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["appointments"] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}

export function useUpdateAppointment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<AppointmentCreate & { status?: string }> }) =>
      api.patch<Appointment>(`/appointments/${id}`, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["appointments"] })
      queryClient.invalidateQueries({ queryKey: ["appointments", variables.id] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}

export function useDeleteAppointment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/appointments/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["appointments"] })
    },
    onError: (err: Error) => { toast.error(err.message) },
  })
}

export function useAvailableSlots(doktorId: string, date: string, duration = 30) {
  return useQuery({
    queryKey: ["appointments", "available-slots", doktorId, date, duration],
    queryFn: () =>
      api.get<AvailableSlot[]>(
        `/appointments/available-slots?doktor_id=${doktorId}&date=${date}&trajanje_minuta=${duration}`,
      ),
    enabled: !!doktorId && !!date,
  })
}


