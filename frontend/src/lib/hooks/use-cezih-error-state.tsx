import { useSyncExternalStore } from "react"

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
