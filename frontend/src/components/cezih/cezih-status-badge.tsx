"use client"

import { AlertTriangle, CheckCircle2, Clock, FileText, XCircle, type LucideIcon } from "lucide-react"

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn, formatDateTimeHR } from "@/lib/utils"
import { useRecordTypeMaps } from "@/lib/hooks/use-record-types"
import type { MedicalRecord } from "@/lib/types"

export type CezihLifecycleState = "lokalno" | "ceka_slanje" | "greska" | "aktivan" | "storniran"

type BadgeRecord = Pick<
  MedicalRecord,
  | "cezih_sent"
  | "cezih_storno"
  | "tip"
  | "cezih_last_error_code"
  | "cezih_last_error_display"
  | "cezih_last_error_at"
>

export function deriveCezihState(
  record: BadgeRecord,
  isCezihMandatory: Set<string>,
): CezihLifecycleState {
  if (record.cezih_storno) return "storniran"
  if (record.cezih_sent) return "aktivan"
  // A populated error column means a send was attempted and failed — that is
  // true regardless of whether the tip is mandatory, so it wins over ceka_slanje.
  if (record.cezih_last_error_code) return "greska"
  if (isCezihMandatory.has(record.tip)) return "ceka_slanje"
  return "lokalno"
}

const LABELS: Record<CezihLifecycleState, string> = {
  lokalno: "Samo lokalno",
  ceka_slanje: "Čeka slanje",
  greska: "Greška pri slanju",
  aktivan: "e-Nalaz poslan",
  storniran: "Storniran",
}

const ICONS: Record<CezihLifecycleState, LucideIcon> = {
  lokalno: FileText,
  ceka_slanje: Clock,
  greska: AlertTriangle,
  aktivan: CheckCircle2,
  storniran: XCircle,
}

const COLORS: Record<CezihLifecycleState, string> = {
  lokalno: "bg-slate-100 text-slate-700 border-slate-200",
  ceka_slanje: "bg-amber-100 text-amber-800 border-amber-200",
  greska: "bg-red-100 text-red-800 border-red-200",
  aktivan: "bg-emerald-100 text-emerald-800 border-emerald-200",
  storniran: "bg-red-100 text-red-800 border-red-200",
}

interface CezihStatusBadgeProps {
  record: BadgeRecord
  size?: "sm" | "md"
  showIcon?: boolean
  labelClassName?: string
  className?: string
}

export function CezihStatusBadge({
  record,
  size = "sm",
  showIcon = true,
  labelClassName,
  className,
}: CezihStatusBadgeProps) {
  const { isCezihMandatory } = useRecordTypeMaps()
  const state = deriveCezihState(record, isCezihMandatory)
  const Icon = ICONS[state]
  const label = LABELS[state]

  const sizeClasses = size === "md" ? "text-sm px-2.5 py-1 gap-1.5" : "text-xs px-2 py-0.5 gap-1"
  const iconSize = size === "md" ? "h-4 w-4" : "h-3 w-3"

  const badge = (
    <span
      className={cn(
        "inline-flex items-center rounded-md border font-medium",
        sizeClasses,
        COLORS[state],
        className,
      )}
      title={label}
    >
      {showIcon && <Icon className={cn(iconSize, "shrink-0")} aria-hidden />}
      <span className={labelClassName}>{label}</span>
    </span>
  )

  if (state !== "greska") return badge

  return (
    <Popover>
      <PopoverTrigger aria-label={label}>{badge}</PopoverTrigger>
      <PopoverContent align="start" className="w-72 space-y-1">
        <p className="text-sm font-medium text-destructive">Greška pri slanju na CEZIH</p>
        <p className="text-sm">
          {record.cezih_last_error_display || "Nepoznata greška"}
        </p>
        {record.cezih_last_error_code && (
          <p className="text-xs text-muted-foreground">Šifra: {record.cezih_last_error_code}</p>
        )}
        {record.cezih_last_error_at && (
          <p className="text-xs text-muted-foreground">
            Vrijeme: {formatDateTimeHR(record.cezih_last_error_at)}
          </p>
        )}
        <p className="pt-1 text-xs text-muted-foreground">
          Nalaz je spremljen lokalno. Ponovno pošaljite kada je veza s CEZIH-om uspostavljena.
        </p>
      </PopoverContent>
    </Popover>
  )
}
