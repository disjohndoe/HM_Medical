"use client"

import { Shield, FileText, Pill, ArrowDownToLine, Clock, Calendar, Folder, UserPlus } from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { MockBadge } from "@/components/cezih/mock-badge"
import { useCezihActivity } from "@/lib/hooks/use-cezih"
import { CEZIH_ACTION_LABELS, CEZIH_ACTION_COLORS } from "@/lib/constants"

const ACTION_ICONS: Record<string, typeof Shield> = {
  insurance_check: Shield,
  e_nalaz_send: FileText,
  e_uputnica_retrieve: ArrowDownToLine,
  e_recept_send: Pill,
  visit_create: Calendar,
  visit_update: Calendar,
  visit_close: Calendar,
  visit_reopen: Calendar,
  visit_cancel: Calendar,
  case_create: Folder,
  case_retrieve: Folder,
  case_update: Folder,
  case_remission: Folder,
  case_relapse: Folder,
  case_resolve: Folder,
  case_reopen: Folder,
  case_delete: Folder,
  foreigner_register: UserPlus,
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

export function CezihActivityLog() {
  const { data, isLoading } = useCezihActivity(15)

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div className="flex items-center gap-2">
          <CardTitle className="text-lg">Aktivnost</CardTitle>
          <MockBadge />
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
                    {details && (
                      <p className="mt-0.5 text-xs text-muted-foreground truncate">
                        {item.action === "insurance_check" && details.mbo && `MBO: ${details.mbo}`}
                        {item.action === "e_nalaz_send" && details.reference_id && `Ref: ${details.reference_id}`}
                        {item.action === "e_uputnica_retrieve" && details.count && `${details.count} uputnica`}
                        {item.action === "e_recept_send" && details.recept_id && `ID: ${details.recept_id}`}
                        {item.action.startsWith("visit_") && details.visit_id && `ID: ${details.visit_id}`}
                        {item.action.startsWith("case_") && details.case_id && `ID: ${details.case_id}`}
                        {item.action.startsWith("case_") && !details.case_id && details.mbo && `MBO: ${details.mbo}`}
                        {item.action === "foreigner_register" && details.mbo && `MBO: ${details.mbo}`}
                      </p>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
