"use client"

import { CheckCircle2, Clock, FileText, XCircle, type LucideIcon } from "lucide-react"

import { cn } from "@/lib/utils"
import { useRecordTypeMaps } from "@/lib/hooks/use-record-types"
import type { MedicalRecord } from "@/lib/types"

export type CezihLifecycleState = "lokalno" | "ceka_slanje" | "aktivan" | "storniran"

export function deriveCezihState(
  record: Pick<MedicalRecord, "cezih_sent" | "cezih_storno" | "tip">,
  isCezihMandatory: Set<string>,
): CezihLifecycleState {
  if (record.cezih_storno) return "storniran"
  if (record.cezih_sent) return "aktivan"
  if (isCezihMandatory.has(record.tip)) return "ceka_slanje"
  return "lokalno"
}

const LABELS: Record<CezihLifecycleState, string> = {
  lokalno: "Samo lokalno",
  ceka_slanje: "Čeka slanje",
  aktivan: "e-Nalaz aktivan",
  storniran: "Storniran",
}

const ICONS: Record<CezihLifecycleState, LucideIcon> = {
  lokalno: FileText,
  ceka_slanje: Clock,
  aktivan: CheckCircle2,
  storniran: XCircle,
}

const COLORS: Record<CezihLifecycleState, string> = {
  lokalno: "bg-slate-100 text-slate-700 border-slate-200",
  ceka_slanje: "bg-amber-100 text-amber-800 border-amber-200",
  aktivan: "bg-emerald-100 text-emerald-800 border-emerald-200",
  storniran: "bg-red-100 text-red-800 border-red-200",
}

interface CezihStatusBadgeProps {
  record: Pick<MedicalRecord, "cezih_sent" | "cezih_storno" | "tip">
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

  return (
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
}
