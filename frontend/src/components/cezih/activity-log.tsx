"use client"

import { useState } from "react"
import { Shield, FileText, Pill, Clock, Folder, UserPlus } from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { TablePagination } from "@/components/shared/table-pagination"
import { useCezihActivity } from "@/lib/hooks/use-cezih"
import { CEZIH_ACTION_LABELS, CEZIH_ACTION_COLORS } from "@/lib/constants"

const ACTION_ICONS: Record<string, typeof Shield> = {
  insurance_check: Shield,
  e_nalaz_send: FileText,
  e_recept_send: Pill,
  case_create: Folder,
  case_retrieve: Folder,
  case_update: Folder,
  case_remission: Folder,
  case_relapse: Folder,
  case_resolve: Folder,
  case_reopen: Folder,
  case_delete: Folder,
  foreigner_register: UserPlus,
  e_nalaz_cancel: FileText,
  e_nalaz_replace: FileText,
}

function formatDetail(details: Record<string, string>): string | null {
  if (details.reference_id) return `Ref: ${details.reference_id}`
  if (details.original) return `Ref: ${details.original}`
  if (details.visit_id) return `ID: ${details.visit_id}`
  if (details.case_id) return `ID: ${details.case_id}`
  if (details.recept_id) return `ID: ${details.recept_id}`
  if (details.mbo) return `MBO: ${details.mbo}`
  return null
}

function timeAgo(dateStr: string): string {
  const now = new Date()
  const date = new Date(dateStr)
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000)

  if (seconds < 60) return "upravo sada"
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `prije ${minutes} min`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `prije ${hours} h`
  const days = Math.floor(hours / 24)
  return `prije ${days} d`
}

function parseDetails(details: string | null): Record<string, string> | null {
  if (!details) return null
  try {
    return JSON.parse(details)
  } catch {
    return null
  }
}

const PAGE_SIZE = 20

export function CezihActivityLog() {
  const [page, setPage] = useState(0)
  const { data, isLoading, isError, error } = useCezihActivity(page * PAGE_SIZE, PAGE_SIZE)

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div className="flex items-center gap-2">
          <CardTitle className="text-lg">Aktivnost</CardTitle>
        </div>
        <Clock className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3">
                <Skeleton className="h-8 w-8 rounded-full" />
                <div className="flex-1 space-y-1">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-3 w-20" />
                </div>
              </div>
            ))}
          </div>
        ) : isError ? (
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3">
            <p className="text-sm text-destructive">
              Greška pri dohvatu aktivnosti: {(error as Error)?.message ?? "Nepoznata greška"}
            </p>
          </div>
        ) : !data?.items.length ? (
          <p className="text-sm text-muted-foreground text-center py-6">
            Nema CEZIH aktivnosti. Izvršite operaciju da biste vidjeli zapis.
          </p>
        ) : (
          <div className="space-y-3">
            {data.items.map((item) => {
              const Icon = ACTION_ICONS[item.action] || FileText
              const colorClass = CEZIH_ACTION_COLORS[item.action] || "bg-gray-100 text-gray-800"
              const details = parseDetails(item.details)

              return (
                <div key={item.id} className="flex items-start gap-3">
                  <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${colorClass.split(" ")[0]}`}>
                    <Icon className="h-4 w-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className={`text-xs ${colorClass}`}>
                        {CEZIH_ACTION_LABELS[item.action] || item.action}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {timeAgo(item.created_at)}
                      </span>
                    </div>
                    {details && formatDetail(details) && (
                      <p className="mt-0.5 text-xs text-muted-foreground truncate">
                        {formatDetail(details)}
                      </p>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
          {data.total > PAGE_SIZE && (
            <div className="pt-3">
              <TablePagination
                page={page}
                pageSize={PAGE_SIZE}
                total={data.total}
                onPageChange={setPage}
              />
            </div>
          )}
        )}
      </CardContent>
    </Card>
  )
}
