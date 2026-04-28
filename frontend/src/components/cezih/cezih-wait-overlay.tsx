"use client"

import { CEZIH_WAIT_TITLE, CEZIH_WAIT_SUBTITLE } from "@/lib/constants"

interface Props {
  isOpen: boolean
  message?: string
  subMessage?: string
}

export function CezihWaitOverlay({
  isOpen,
  message = CEZIH_WAIT_TITLE,
  subMessage = CEZIH_WAIT_SUBTITLE,
}: Props) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-hidden={!isOpen}
      className={
        "absolute inset-0 z-20 flex items-center justify-center rounded-[inherit] " +
        "bg-background/70 backdrop-blur-sm transition-opacity duration-200 " +
        (isOpen
          ? "opacity-100 pointer-events-auto"
          : "opacity-0 pointer-events-none")
      }
    >
      <div className="flex min-w-[300px] max-w-[360px] flex-col items-center gap-3 rounded-xl border bg-card px-6 py-5 shadow-lg">
        <EkgSpinner />
        <p className="text-sm font-semibold text-foreground">{message}</p>
        <p className="max-w-[280px] text-center text-xs text-muted-foreground">
          {subMessage}
        </p>
      </div>
    </div>
  )
}

function EkgSpinner() {
  return (
    <svg
      viewBox="0 0 200 60"
      className="ekg-glow h-12 w-40 text-emerald-600"
      aria-hidden="true"
    >
      {/* baseline */}
      <line
        x1="0"
        y1="30"
        x2="200"
        y2="30"
        stroke="currentColor"
        strokeWidth="0.5"
        strokeOpacity="0.2"
      />
      {/* ECG trace */}
      <polyline
        points="0,30 40,30 50,30 58,18 66,46 74,12 82,40 92,30 130,30 138,24 146,36 154,30 200,30"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="ekg-trace"
      />
    </svg>
  )
}
