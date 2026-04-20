export type CezihActionStatus = "ok" | "pending" | "error"

export interface CezihRowStatus {
  status: CezihActionStatus
  lastErrorCode?: string
  lastErrorDisplay?: string
  lastErrorDiagnostics?: string
  lastErrorAt?: string
}

type CezihRowLike = {
  visit_id?: string
  case_id?: string
  id?: string
  last_error_code?: string | null
  last_error_display?: string | null
  last_error_diagnostics?: string | null
  last_error_at?: string | null
  cezih_last_error_code?: string | null
  cezih_last_error_display?: string | null
  cezih_last_error_diagnostics?: string | null
  cezih_last_error_at?: string | null
  _local?: boolean
}

/** Derive the unified action-status shape for a CEZIH row.
 *  Optimistic temp rows (`temp-*` / `pending-*` / `_local`) → "pending";
 *  DB error columns populated → "error";
 *  otherwise → "ok". */
export function deriveCezihRowStatus(row: CezihRowLike): CezihRowStatus {
  const rowId = row.visit_id ?? row.case_id ?? row.id ?? ""
  if (row._local || rowId.startsWith("temp-") || rowId.startsWith("pending-")) {
    return { status: "pending" }
  }
  const code = row.last_error_code ?? row.cezih_last_error_code ?? null
  if (code) {
    return {
      status: "error",
      lastErrorCode: code,
      lastErrorDisplay: row.last_error_display ?? row.cezih_last_error_display ?? undefined,
      lastErrorDiagnostics: row.last_error_diagnostics ?? row.cezih_last_error_diagnostics ?? undefined,
      lastErrorAt: row.last_error_at ?? row.cezih_last_error_at ?? undefined,
    }
  }
  return { status: "ok" }
}
