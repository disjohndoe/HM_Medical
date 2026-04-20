import { useState, useSyncExternalStore } from "react"
import { AlertTriangle, ChevronDown, ChevronUp, Copy, Check } from "lucide-react"

export type CezihRowError = {
  rowId: string
  message: string
  cezihCode?: string
  diagnostics?: string
  timestamp: number
}

const store = new Map<string, CezihRowError>()
let version = 0
const listeners = new Set<() => void>()

function emitChange() {
  version++
  for (const l of listeners) l()
}

function subscribe(cb: () => void) {
  listeners.add(cb)
  return () => { listeners.delete(cb) }
}

function getSnapshot() {
  return version
}

export function setError(
  rowId: string,
  message: string,
  cezihCode?: string,
  diagnostics?: string,
) {
  store.set(rowId, { rowId, message, cezihCode, diagnostics, timestamp: Date.now() })
  emitChange()
}

export function clearError(rowId: string) {
  if (store.delete(rowId)) emitChange()
}

export function getError(rowId: string): CezihRowError | undefined {
  return store.get(rowId)
}

export function useCezihRowError(rowId?: string) {
  useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
  if (!rowId) return undefined
  return store.get(rowId)
}

/** Sync DB-backed error payloads into the in-memory store after a refetch.
 *  Pass the full row list; rows with a non-null code become stored errors,
 *  rows without are cleared. Server state is the source of truth. */
export function syncCezihRowErrors<
  T extends {
    last_error_code?: string | null
    last_error_display?: string | null
    last_error_diagnostics?: string | null
    cezih_last_error_code?: string | null
    cezih_last_error_display?: string | null
    cezih_last_error_diagnostics?: string | null
  },
>(
  rows: T[],
  idOf: (row: T) => string | undefined,
) {
  let changed = false
  const seen = new Set<string>()
  for (const row of rows) {
    const rowId = idOf(row)
    if (!rowId) continue
    seen.add(rowId)
    const code = row.last_error_code ?? row.cezih_last_error_code ?? null
    const display = row.last_error_display ?? row.cezih_last_error_display ?? ""
    const diagnostics = row.last_error_diagnostics ?? row.cezih_last_error_diagnostics ?? ""
    if (code) {
      const existing = store.get(rowId)
      const next: CezihRowError = {
        rowId,
        message: display || "Greška na CEZIH-u, pokušajte ponovno",
        cezihCode: code,
        diagnostics: diagnostics || undefined,
        timestamp: existing?.timestamp ?? Date.now(),
      }
      if (
        !existing
        || existing.message !== next.message
        || existing.cezihCode !== next.cezihCode
        || existing.diagnostics !== next.diagnostics
      ) {
        store.set(rowId, next)
        changed = true
      }
    } else if (store.has(rowId)) {
      store.delete(rowId)
      changed = true
    }
  }
  if (changed) emitChange()
}

function errorLabel(err: CezihRowError): string {
  // ERR_DOCTRANSVAL_1000 = CEZIH internal gateway/backend timeout on replace
  // or cancel. The document is still live on their side; retrying the same
  // action later typically succeeds.
  if (err.cezihCode === "ERR_DOCTRANSVAL_1000") {
    return "Greška na CEZIH-u, pokušajte poslati nalaz ponovno"
  }
  return "Greška na CEZIH-u, pokušajte ponovno"
}

/** Inline error badge for CEZIH table rows. Must be a component (hook in map). */
export function CezihRowErrorBadge({ rowId }: { rowId: string }) {
  const err = useCezihRowError(rowId)
  const [expanded, setExpanded] = useState(false)
  const [copied, setCopied] = useState(false)
  if (!err) return null

  const hasDetails = Boolean(err.cezihCode || err.diagnostics)

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation()
    const text = [err.cezihCode, err.diagnostics].filter(Boolean).join("\n")
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      /* ignore */
    }
  }

  return (
    <div
      className="mt-1 overflow-hidden rounded border border-red-300 bg-red-50 text-xs text-red-900 shadow-sm"
      role="alert"
    >
      <button
        type="button"
        onClick={() => hasDetails && setExpanded((v) => !v)}
        className={`flex w-full items-center gap-1.5 px-2 py-1 text-left font-medium ${
          hasDetails ? "cursor-pointer hover:bg-red-100" : "cursor-default"
        }`}
        aria-expanded={expanded}
      >
        <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-red-700" aria-hidden="true" />
        <span className="flex-1">{errorLabel(err)}</span>
        {hasDetails && (expanded
          ? <ChevronUp className="h-3.5 w-3.5 shrink-0 text-red-700" aria-hidden="true" />
          : <ChevronDown className="h-3.5 w-3.5 shrink-0 text-red-700" aria-hidden="true" />
        )}
      </button>
      {expanded && hasDetails && (
        <div className="border-t border-red-200 bg-red-100/60 px-2 py-1.5">
          {err.cezihCode && (
            <div className="flex items-center gap-1.5">
              <code className="flex-1 font-mono text-[11px] text-red-900 break-all">
                {err.cezihCode}
              </code>
              <button
                type="button"
                onClick={handleCopy}
                className="shrink-0 rounded p-0.5 text-red-700 hover:bg-red-200"
                title="Kopiraj kod greške"
                aria-label="Kopiraj kod greške"
              >
                {copied
                  ? <Check className="h-3 w-3" aria-hidden="true" />
                  : <Copy className="h-3 w-3" aria-hidden="true" />}
              </button>
            </div>
          )}
          {err.diagnostics && (
            <div className="mt-1 whitespace-pre-wrap break-words text-[11px] text-red-800">
              {err.diagnostics}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
