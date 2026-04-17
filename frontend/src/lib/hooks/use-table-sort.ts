"use client"

import { useCallback, useMemo, useState } from "react"

export type SortDir = "asc" | "desc"

export interface UseTableSortOptions<T> {
  defaultKey: string
  defaultDir?: SortDir
  keyAccessors?: Record<string, (row: T) => unknown>
  primaryBucket?: (row: T) => number
}

export interface UseTableSortResult<T> {
  sorted: T[]
  sortKey: string
  sortDir: SortDir
  toggleSort: (key: string) => void
}

function accessorFor<T>(
  key: string,
  keyAccessors: Record<string, (row: T) => unknown> | undefined,
): (row: T) => unknown {
  const override = keyAccessors?.[key]
  if (override) return override
  return (row: T) => (row as Record<string, unknown>)[key]
}

function toSortable(value: unknown): number | string | null {
  if (value === null || value === undefined) return null
  if (value instanceof Date) return value.getTime()
  if (typeof value === "number") return Number.isFinite(value) ? value : null
  if (typeof value === "boolean") return value ? 1 : 0
  if (typeof value === "string") {
    const trimmed = value.trim()
    if (trimmed === "") return null
    // ISO date heuristic: 2026-04-17 or 2026-04-17T...
    if (/^\d{4}-\d{2}-\d{2}/.test(trimmed)) {
      const ms = Date.parse(trimmed)
      if (!Number.isNaN(ms)) return ms
    }
    return trimmed.toLocaleLowerCase("hr")
  }
  return null
}

function compareValues(a: unknown, b: unknown, dir: SortDir): number {
  const av = toSortable(a)
  const bv = toSortable(b)
  if (av === null && bv === null) return 0
  if (av === null) return 1 // nulls always last regardless of direction
  if (bv === null) return -1
  let cmp: number
  if (typeof av === "number" && typeof bv === "number") {
    cmp = av - bv
  } else {
    cmp = String(av).localeCompare(String(bv), "hr")
  }
  return dir === "asc" ? cmp : -cmp
}

export function useTableSort<T>(
  data: T[] | undefined,
  opts: UseTableSortOptions<T>,
): UseTableSortResult<T> {
  const { defaultKey, defaultDir = "desc", keyAccessors, primaryBucket } = opts

  const [sortKey, setSortKey] = useState(defaultKey)
  const [sortDir, setSortDir] = useState<SortDir>(defaultDir)

  const toggleSort = useCallback(
    (key: string) => {
      if (key === sortKey) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"))
      } else {
        setSortKey(key)
        setSortDir("desc")
      }
    },
    [sortKey],
  )

  const sorted = useMemo(() => {
    if (!data || data.length === 0) return []
    const accessor = accessorFor<T>(sortKey, keyAccessors)
    const indexed = data.map((row, index) => ({ row, index }))
    indexed.sort((a, b) => {
      if (primaryBucket) {
        const bucketCmp = primaryBucket(a.row) - primaryBucket(b.row)
        if (bucketCmp !== 0) return bucketCmp
      }
      const cmp = compareValues(accessor(a.row), accessor(b.row), sortDir)
      if (cmp !== 0) return cmp
      return a.index - b.index // stable
    })
    return indexed.map((x) => x.row)
  }, [data, sortKey, sortDir, keyAccessors, primaryBucket])

  return { sorted, sortKey, sortDir, toggleSort }
}
