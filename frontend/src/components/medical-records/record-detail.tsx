"use client"

import { useState } from "react"
import { Send, Loader2, PencilIcon, Pill, XCircle, RefreshCw } from "lucide-react"
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
import { RECORD_TIP, RECORD_TIP_COLORS, CEZIH_ELIGIBLE_TYPES, CEZIH_MANDATORY_TYPES } from "@/lib/constants"
import { formatDateHR, formatDateTimeHR, formatCurrencyEUR } from "@/lib/utils"
import { useSendENalaz, useCancelDocument, useReplaceDocument } from "@/lib/hooks/use-cezih"
import { usePermissions } from "@/lib/hooks/use-permissions"
import { usePerformedProcedures } from "@/lib/hooks/use-procedures"
import { MockBadge } from "@/components/cezih/mock-badge"
import { PrescriptionForm } from "@/components/prescriptions/prescription-form"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import type { MedicalRecord } from "@/lib/types"

interface RecordDetailProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  record: MedicalRecord
  patientId: string
  onEdit: () => void
}

export function RecordDetail({ open, onOpenChange, record, patientId, onEdit }: RecordDetailProps) {
  const sendENalaz = useSendENalaz()
  const cancelDocument = useCancelDocument()
  const replaceDocument = useReplaceDocument()
  const { canPerformCezihOps, canEditMedicalRecord, canUseHzzo } = usePermissions()
  const [eReceptOpen, setEReceptOpen] = useState(false)
  const [confirmCancel, setConfirmCancel] = useState(false)
  const [confirmReplace, setConfirmReplace] = useState(false)

  const handleSendENalaz = () => {
    sendENalaz.mutate(
      {
        patient_id: patientId,
        record_id: record.id,
      },
      {
        onSuccess: () => {
          toast.success("e-Nalaz poslan na CEZIH")
        },
        onError: (err) => toast.error(err.message),
      },
    )
  }

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
    replaceDocument.mutate(record.cezih_reference_id, {
      onSuccess: () => {
        toast.success("Dokument zamijenjen na CEZIH")
        setConfirmReplace(false)
      },
      onError: (err) => toast.error(err.message),
    })
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
              className={RECORD_TIP_COLORS[record.tip] || ""}
            >
              {RECORD_TIP[record.tip] || record.tip}
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

          <Separator />

          {canPerformCezihOps && (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <h4 className="text-sm font-medium text-muted-foreground">CEZIH status</h4>
              <MockBadge />
            </div>
            {!CEZIH_ELIGIBLE_TYPES.has(record.tip) ? (
              <p className="text-xs text-muted-foreground">
                Ovaj tip zapisa ({RECORD_TIP[record.tip] || record.tip}) nije predviđen za slanje na CEZIH.
              </p>
            ) : record.cezih_sent ? (
              <div className="space-y-2">
                {record.cezih_storno ? (
                  <Badge className="bg-red-100 text-red-800 border-red-200">
                    Storniran na CEZIH
                  </Badge>
                ) : (
                  <Badge className="bg-green-100 text-green-800 border-green-200">
                    Poslano na CEZIH
                  </Badge>
                )}
                {record.cezih_reference_id && (
                  <p className="text-xs text-muted-foreground">
                    Referenca: <span className="font-mono">{record.cezih_reference_id}</span>
                  </p>
                )}
                {record.cezih_sent_at && (
                  <p className="text-xs text-muted-foreground">
                    Vrijeme: {formatDateTimeHR(record.cezih_sent_at)}
                  </p>
                )}
                {record.cezih_reference_id && !record.cezih_storno && (
                  <div className="flex gap-2 pt-1">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setConfirmReplace(true)}
                      disabled={replaceDocument.isPending}
                    >
                      {replaceDocument.isPending ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <RefreshCw className="mr-2 h-4 w-4" />
                      )}
                      Zamijeni
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => setConfirmCancel(true)}
                      disabled={cancelDocument.isPending}
                    >
                      {cancelDocument.isPending ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <XCircle className="mr-2 h-4 w-4" />
                      )}
                      Storniraj
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-2">
                {CEZIH_MANDATORY_TYPES.has(record.tip) && (
                  <div className="rounded-md bg-amber-50 border border-amber-200 px-3 py-2">
                    <p className="text-xs font-medium text-amber-800">
                      Obavezno slanje na CEZIH (čl. 23, NN 14/2019)
                    </p>
                  </div>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSendENalaz}
                  disabled={sendENalaz.isPending}
                >
                  {sendENalaz.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="mr-2 h-4 w-4" />
                  )}
                  Pošalji e-Nalaz
                </Button>
              </div>
            )}
          </div>
          )}

          {canPerformCezihOps && (
          <>
          <Separator />

          {/* e-Recept button */}
          {canUseHzzo && (
          <>
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <h4 className="text-sm font-medium text-muted-foreground">e-Recept</h4>
              <MockBadge />
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setEReceptOpen(true)}
            >
              <Pill className="mr-2 h-4 w-4" />
              Pošalji e-Recept
            </Button>
          </div>

          <Separator />
          </>
          )}
          </>
          )}

          <div className="text-xs text-muted-foreground">
            Kreiran: {formatDateTimeHR(record.created_at)}
          </div>
          {record.updated_at !== record.created_at && (
            <div className="text-xs text-muted-foreground">
              Zadnja izmjena: {formatDateTimeHR(record.updated_at)}
            </div>
          )}

          {canEditMedicalRecord && (
          <div className="pt-4">
            <Button variant="outline" className="w-full" onClick={onEdit}>
              <PencilIcon className="mr-2 h-4 w-4" />
              Uredi zapis
            </Button>
          </div>
          )}
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
    </Sheet>
  )
}
