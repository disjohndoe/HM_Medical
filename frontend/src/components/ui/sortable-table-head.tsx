"use client"

import { ChevronDown, ChevronUp, ChevronsUpDown } from "lucide-react"
import type { KeyboardEvent } from "react"

import { TableHead } from "@/components/ui/table"
import { cn } from "@/lib/utils"

import type { SortDir } from "@/lib/hooks/use-table-sort"

interface SortableTableHeadProps {
  columnKey: string
  label: string
  currentKey: string
  currentDir: SortDir
  onSort: (key: string) => void
  className?: string
  sortable?: boolean
}

export function SortableTableHead({
  columnKey,
  label,
  currentKey,
  currentDir,
  onSort,
  className,
  sortable = true,
}: SortableTableHeadProps) {
  if (!sortable) {
    return <TableHead className={className}>{label}</TableHead>
  }

  const isActive = currentKey === columnKey
  const Icon = isActive ? (currentDir === "asc" ? ChevronUp : ChevronDown) : ChevronsUpDown

  const handleKeyDown = (event: KeyboardEvent<HTMLTableCellElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault()
      onSort(columnKey)
    }
  }

  return (
    <TableHead
      role="button"
      tabIndex={0}
      aria-sort={isActive ? (currentDir === "asc" ? "ascending" : "descending") : "none"}
      onClick={() => onSort(columnKey)}
      onKeyDown={handleKeyDown}
      className={cn(
        "cursor-pointer select-none hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
        className,
      )}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        <Icon
          className={cn(
            "h-3.5 w-3.5 transition-opacity",
            isActive ? "opacity-100" : "opacity-40",
          )}
        />
      </span>
    </TableHead>
  )
}
