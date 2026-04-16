"use client"

import { useState } from "react"
import { Send, Loader2, PencilIcon, Pill, XCircle, RefreshCw, Download } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"
import { formatDateHR, formatDateTimeHR, formatCurrencyEUR } from "@/lib/utils"
import { api } from "@/lib/api-client"
import { useCancelDocument, useReplaceDocument } from "@/lib/hooks/use-cezih"
import { useRecordTypeMaps } from "@/lib/hooks/use-record-types"
import { usePermissions } from "@/lib/hooks/use-permissions"
import { usePerformedProcedures } from "@/lib/hooks/use-procedures"
import { PrescriptionForm } from "@/components/prescriptions/prescription-form"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { SendNalazDialog } from "@/components/cezih/send-nalaz-dialog"
import {
  CezihStatusBadge,
  deriveCezihState,
} from "@/components/cezih/cezih-status-badge"
import type { MedicalRecord } from "@/lib/types"

interface RecordDetailProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  record: MedicalRecord
  patientId: string
  patientMbo?: string | null
  onEdit: () => void
}

export function RecordDetail({ open, onOpenChange, record, patientId, patientMbo, onEdit }: RecordDetailProps) {
  const cancelDocument = useCancelDocument()
  const replaceDocument = useReplaceDocument()
  const { canPerformCezihOps, canEditMedicalRecord, canUseHzzo } = usePermissions()
  const [eReceptOpen, setEReceptOpen] = useState(false)
  const [confirmCancel, setConfirmCancel] = useState(false)
  const [confirmReplace, setConfirmReplace] = useState(false)
  const [pdfLoading, setPdfLoading] = useState(false)
  const [sendNalazOpen, setSendNalazOpen] = useState(false)

  const { tipLabelMap, tipColorMap, isCezihMandatory, isCezihEligible } = useRecordTypeMaps()
  const cezihState = deriveCezihState(record, isCezihMandatory)
  const cezihEligible = isCezihEligible.has(record.tip)

  const handleCancelDocument = () => {
    if (!record.cezih_reference_id) return
    cancelDocument.mutate(record.cezih_reference_id, {
      onSuccess: () => {
        toast.success("e-Nalaz storniran na CEZIH")
        setConfirmCancel(false)
      },
      onError: (err) => toast.error(err.message),
    })
  }

  const handleReplaceDocument = () => {
    if (!record.cezih_reference_id) return
    replaceDocument.mutate({ referenceId: record.cezih_reference_id, record_id: record.id }, {
      onSuccess: () => {
        toast.success("Dokument zamijenjen na CEZIH")
        setConfirmReplace(false)
      },
      onError: (err) => toast.error(err.message),
    })
  }

  const handleDownloadPdf = async () => {
    setPdfLoading(true)
    try {
      const res = await api.fetchRaw(`/medical-records/${record.id}/pdf`)
      const blob = await res.blob()
      const disposition = res.headers.get("content-disposition") || ""
      const match = disposition.match(/filename="?([^"]+)"?/)
      const filename = match ? match[1] : `nalaz_${record.datum}_${record.id.slice(0, 4)}.pdf`
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Greška pri preuzimanju PDF-a")
    } finally {
      setPdfLoading(false)
    }
  }


  const { data: linkedProcedures } = usePerformedProcedures(
    undefined, undefined, undefined, undefined, record.id,
  )
  const linkedItems = linkedProcedures?.items ?? []

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="center">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Badge
              variant="secondary"
              className={tipColorMap[record.tip] || ""}
            >
              {tipLabelMap[record.tip] || record.tip}
            </Badge>
            <span>{formatDateHR(record.datum)}</span>
          </SheetTitle>
          <SheetDescription>
            {record.doktor_ime
              ? `dr. ${record.doktor_prezime} ${record.doktor_ime}`
              : "—"}
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-4 px-4">
          {canPerformCezihOps && cezihEligible && (
            <div className="rounded-lg border bg-muted/30 px-3 py-2.5 space-y-1.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <CezihStatusBadge record={record} size="md" showIcon />
                {cezihState === "aktivan" && record.cezih_sent_at && (
                  <span className="text-xs text-muted-foreground">
                    Poslano {formatDateTimeHR(record.cezih_sent_at)}
                  </span>
                )}
                {cezihState === "storniran" && record.cezih_sent_at && (
                  <span className="text-xs text-muted-foreground">
                    Storniran {formatDateTimeHR(record.cezih_sent_at)}
                  </span>
                )}
              </div>
              {cezihState === "aktivan" && record.cezih_reference_id && (
                <p className="text-[11px] text-muted-foreground font-mono truncate" title={record.cezih_reference_id}>
                  Ref: {record.cezih_reference_id}
                </p>
              )}
              {cezihState === "ceka_slanje" && (
                <p className="text-xs text-amber-800">
                  Obavezno slanje na CEZIH (čl. 23, NN 14/2019)
                </p>
              )}
              {cezihState === "lokalno" && (
                <p className="text-xs text-muted-foreground">
                  Postoji samo u lokalnoj evidenciji.
                </p>
              )}
            </div>
          )}
          {canPerformCezihOps && !cezihEligible && (
            <p className="text-xs text-muted-foreground">
              Ovaj tip zapisa ({tipLabelMap[record.tip] || record.tip}) ne šalje se na CEZIH.
            </p>
          )}

          {record.dijagnoza_tekst && (
            <div>
              <h4 className="text-sm font-medium text-muted-foreground">Dijagnoza</h4>
              <p className="mt-1 text-sm">
                {record.dijagnoza_mkb && (
                  <Badge variant="outline" className="mr-2 font-mono text-xs">
                    {record.dijagnoza_mkb}
                  </Badge>
                )}
                {record.dijagnoza_tekst}
              </p>
            </div>
          )}

          {record.dijagnoza_tekst && <Separator />}

          <div>
            <h4 className="text-sm font-medium text-muted-foreground">Sadržaj</h4>
            <div className="mt-1 whitespace-pre-wrap text-sm leading-relaxed">
              {record.sadrzaj}
            </div>
          </div>

          <Separator />

          {/* Preporučena terapija */}
          {record.preporucena_terapija && record.preporucena_terapija.length > 0 && (
          <>
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-muted-foreground">Preporučena terapija</h4>
            <div className="space-y-1">
              {record.preporucena_terapija.map((lijek, i) => (
                <div key={i} className="flex items-start justify-between rounded-md bg-muted px-3 py-2 text-sm">
                  <div>
                    <span className="font-medium">{lijek.naziv}</span>
                    {lijek.jacina && <span className="ml-1 text-xs text-muted-foreground">{lijek.jacina}</span>}
                    {lijek.oblik && <span className="ml-1 text-xs text-muted-foreground">· {lijek.oblik}</span>}
                  </div>
                  <div className="text-right text-xs text-muted-foreground">
                    {lijek.doziranje && <div>{lijek.doziranje}</div>}
                    {lijek.napomena && <div>{lijek.napomena}</div>}
                  </div>
                </div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground italic">
              Obiteljski liječnik izdaje e-Recept s RS oznakom na temelju ove preporuke.
            </p>
          </div>
          <Separator />
          </>
          )}

          {/* Povezani postupci */}
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-muted-foreground">Povezani postupci</h4>
            {linkedItems.length > 0 ? (
              <div className="space-y-1">
                {linkedItems.map((p) => (
                  <div key={p.id} className="flex items-center justify-between rounded-md bg-muted px-3 py-2 text-sm">
                    <span>
                      <span className="font-mono text-xs text-muted-foreground">{p.procedure_sifra}</span>{" "}
                      {p.procedure_naziv}
                    </span>
                    <span className="text-muted-foreground">{formatCurrencyEUR(p.cijena_cents / 100)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Nema povezanih postupaka</p>
            )}
          </div>

          {canPerformCezihOps && canUseHzzo && (
            <>
              <Separator />
              <div className="space-y-2">
                <h4 className="text-sm font-medium text-muted-foreground">e-Recept</h4>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setEReceptOpen(true)}
                >
                  <Pill className="mr-2 h-4 w-4" />
                  Pošalji e-Recept
                </Button>
              </div>
            </>
          )}

          <Separator />

          <div className="text-xs text-muted-foreground">
            Kreiran: {formatDateTimeHR(record.created_at)}
          </div>
          {record.updated_at !== record.created_at && (
            <div className="text-xs text-muted-foreground">
              Zadnja izmjena: {formatDateTimeHR(record.updated_at)}
            </div>
          )}

          <div className="flex flex-wrap gap-2 pt-4">
            {canPerformCezihOps && cezihEligible && (cezihState === "lokalno" || cezihState === "ceka_slanje") && (
              <Button
                onClick={() => setSendNalazOpen(true)}
                disabled={!patientMbo}
                title={!patientMbo ? "Pacijent nema MBO — potreban za CEZIH" : undefined}
                className="bg-emerald-600 hover:bg-emerald-700 text-white"
              >
                <Send className="mr-2 h-4 w-4" />
                Pošalji e-Nalaz
              </Button>
            )}
            {canPerformCezihOps && cezihState === "aktivan" && record.cezih_reference_id && (
              <>
                <Button
                  variant="outline"
                  onClick={() => setConfirmReplace(true)}
                  disabled={replaceDocument.isPending}
                >
                  {replaceDocument.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className="mr-2 h-4 w-4" />
                  )}
                  Zamijeni e-Nalaz
                </Button>
                <Button
                  variant="outline"
                  className="text-destructive hover:text-destructive"
                  onClick={() => setConfirmCancel(true)}
                  disabled={cancelDocument.isPending}
                >
                  {cancelDocument.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <XCircle className="mr-2 h-4 w-4" />
                  )}
                  Storniraj e-Nalaz
                </Button>
              </>
            )}
            <Button
              variant="outline"
              className="flex-1"
              onClick={handleDownloadPdf}
              disabled={pdfLoading}
            >
              {pdfLoading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Download className="mr-2 h-4 w-4" />
              )}
              Preuzmi PDF
            </Button>
            {canEditMedicalRecord && (
              <Button variant="outline" className="flex-1" onClick={onEdit}>
                <PencilIcon className="mr-2 h-4 w-4" />
                Uredi zapis
              </Button>
            )}
          </div>
        </div>
      </SheetContent>

      <PrescriptionForm
        open={eReceptOpen}
        onOpenChange={setEReceptOpen}
        patientId={patientId}
      />

      <ConfirmDialog
        open={confirmCancel}
        onOpenChange={setConfirmCancel}
        title="Storno e-Nalaza"
        description="Jeste li sigurni da želite stornirati ovaj nalaz na CEZIH? Ova radnja se ne može poništiti."
        confirmLabel="Storniraj"
        variant="destructive"
        onConfirm={handleCancelDocument}
        loading={cancelDocument.isPending}
      />

      <ConfirmDialog
        open={confirmReplace}
        onOpenChange={setConfirmReplace}
        title="Zamjena dokumenta"
        description="Jeste li sigurni da želite zamijeniti ovaj dokument na CEZIH? Stari dokument će biti označen kao zamijenjen."
        confirmLabel="Zamijeni"
        onConfirm={handleReplaceDocument}
        loading={replaceDocument.isPending}
      />

      <SendNalazDialog
        open={sendNalazOpen}
        onOpenChange={setSendNalazOpen}
        patientId={patientId}
        patientMbo={patientMbo ?? null}
        onlyRecordId={record.id}
      />
    </Sheet>
  )
}
