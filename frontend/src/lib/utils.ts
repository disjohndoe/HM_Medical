import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDateHR(date: string | null | undefined): string {
  if (!date) return "—"
  return new Date(date).toLocaleDateString("hr-HR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  })
}

/**
 * Safely extract date portion from ISO string (handles both "YYYY-MM-DD" and "YYYY-MM-DDTHH:MM:SS")
 */
export function toDateOnly(dateStr: string | undefined | null): string | null {
  if (!dateStr) return null
  return dateStr.split("T")[0]
}

export function formatDateTimeHR(date: string | null | undefined): string {
  if (!date) return "—"
  // If date-only string (YYYY-MM-DD), format as date only to avoid UTC midnight interpretation
  if (date.length === 10) {
    return formatDateHR(date)
  }
  return new Date(date).toLocaleString("hr-HR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export function formatCurrencyEUR(amount: number): string {
  return new Intl.NumberFormat("hr-HR", {
    style: "currency",
    currency: "EUR",
  }).format(amount)
}

export function isImage(mimeType: string): boolean {
  return mimeType.startsWith("image/")
}

export function validateOIBChecksum(oib: string): boolean {
  oib = oib.replace(/\s/g, "")
  if (!/^\d{11}$/.test(oib)) return false

  let s = 10
  for (let i = 0; i < 10; i++) {
    const d = parseInt(oib[i])
    s = (s + d) % 10
    if (s === 0) s = 10
    s = (s * 2) % 11
  }

  const check = (11 - s) % 11
  return check === parseInt(oib[10])
}
