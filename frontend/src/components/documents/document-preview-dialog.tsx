"use client"

import { useState, useEffect, useCallback } from "react"
import { Download, Loader2, ZoomIn, ZoomOut, RotateCcw } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useDocumentBlob } from "@/lib/hooks/use-document-blob"
import { isImage } from "@/lib/utils"
import type { Document } from "@/lib/types"

interface DocumentPreviewDialogProps {
  document: Document | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

const MIN_SCALE = 0.5
const MAX_SCALE = 5
const SCALE_STEP = 0.25

export function DocumentPreviewDialog({
  document,
  open,
  onOpenChange,
}: DocumentPreviewDialogProps) {
  const [scale, setScale] = useState(1)
  const { data: blobUrl, isLoading } = useDocumentBlob(open ? document?.id ?? null : null)

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset zoom when dialog closes
    if (!open) setScale(1)
  }, [open])

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    setScale((s) => {
      const next = e.deltaY < 0 ? s + SCALE_STEP : s - SCALE_STEP
      return Math.min(MAX_SCALE, Math.max(MIN_SCALE, next))
    })
  }, [])

  const handleDownload = () => {
    if (!blobUrl || !document) return
    const a = window.document.createElement("a")
    a.href = blobUrl
    a.download = document.naziv
    a.click()
  }

  const isImg = document ? isImage(document.mime_type) : false
  const isPdf = document?.mime_type === "application/pdf"

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-4xl h-[80vh] flex flex-col">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <DialogTitle className="flex-1 truncate">
              {document?.naziv ?? "Pregled dokumenta"}
            </DialogTitle>
          </div>
        </DialogHeader>

        <div className="flex-1 min-h-0 overflow-auto flex items-center justify-center bg-muted/30 rounded-lg">
          {isLoading ? (
            <div className="flex flex-col items-center gap-2">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Učitavanje...</span>
            </div>
          ) : blobUrl && isImg ? (
            <div
              className="overflow-auto w-full h-full flex items-center justify-center"
              onWheel={handleWheel}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={blobUrl}
                alt={document?.naziv ?? ""}
                className="max-w-none transition-transform"
                style={{ transform: `scale(${scale})` }}
                draggable={false}
              />
            </div>
          ) : blobUrl && isPdf ? (
            <object
              data={blobUrl}
              type="application/pdf"
              className="w-full h-full"
            >
              <div className="flex flex-col items-center justify-center gap-2 p-8">
                <p className="text-sm text-muted-foreground">
                  Preglednik ne podržava prikaz PDF-a.
                </p>
                <Button variant="outline" size="sm" onClick={handleDownload}>
                  <Download className="h-4 w-4 mr-1" />
                  Preuzmi PDF
                </Button>
              </div>
            </object>
          ) : (
            <p className="text-sm text-muted-foreground">
              Pregled nije dostupan za ovaj tip datoteke.
            </p>
          )}
        </div>

        {isImg && blobUrl && !isLoading && (
          <div className="flex items-center justify-center gap-2 pt-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setScale((s) => Math.max(MIN_SCALE, s - SCALE_STEP))}
              disabled={scale <= MIN_SCALE}
            >
              <ZoomOut className="h-4 w-4" />
            </Button>
            <span className="text-sm text-muted-foreground w-16 text-center">
              {Math.round(scale * 100)}%
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setScale((s) => Math.min(MAX_SCALE, s + SCALE_STEP))}
              disabled={scale >= MAX_SCALE}
            >
              <ZoomIn className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setScale(1)}
            >
              <RotateCcw className="h-4 w-4" />
            </Button>
            <div className="mx-2 h-4 border-l" />
            <Button variant="outline" size="sm" onClick={handleDownload}>
              <Download className="h-4 w-4 mr-1" />
              Preuzmi
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
