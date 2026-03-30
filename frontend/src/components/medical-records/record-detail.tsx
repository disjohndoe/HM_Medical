"use client"

import { useState } from "react"
import { Send, Loader2, PencilIcon, Pill } from "lucide-react"
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
import { RECORD_TIP, RECORD_TIP_COLORS } from "@/lib/constants"
import { formatDateHR, formatDateTimeHR } from "@/lib/utils"
import { useSendENalaz, useEUputnice, useRetrieveEUputnice } from "@/lib/hooks/use-cezih"
import { usePermissions } from "@/lib/hooks/use-permissions"
import { MockBadge } from "@/components/cezih/mock-badge"
import { ReferralLinkSelect } from "@/components/cezih/referral-link-select"
import { EReceptDialog } from "@/components/cezih/e-recept-dialog"
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
  const { canPerformCezihOps, canEditMedicalRecord } = usePermissions()
  const { data: storedEUputnice } = useEUputnice()
  const retrieveEUputnice = useRetrieveEUputnice()
  const [selectedUputnica, setSelectedUputnica] = useState("")
  const [eReceptOpen, setEReceptOpen] = useState(false)

  const handleSendENalaz = () => {
    sendENalaz.mutate(
      {
        patient_id: patientId,
        record_id: record.id,
        uputnica_id: selectedUputnica && selectedUputnica !== "none" ? selectedUputnica : undefined,
      },
      {
        onSuccess: () => {
          toast.success("e-Nalaz poslan na CEZIH")
        },
        onError: (err) => toast.error(err.message),
      },
    )
  }

  const handleLoadReferrals = () => {
    retrieveEUputnice.mutate(undefined, {
      onError: (err) => toast.error(err.message),
    })
  }

  const referrals = storedEUputnice?.items ?? []

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

        <div className="mt-6 space-y-4">
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

          {canPerformCezihOps && (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <h4 className="text-sm font-medium text-muted-foreground">CEZIH status</h4>
              <MockBadge />
            </div>
            {record.cezih_sent ? (
              <div className="space-y-1">
                <Badge className="bg-green-100 text-green-800 border-green-200">
                  Poslano na CEZIH
                </Badge>
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
              </div>
            ) : (
              <div className="space-y-2">
                {/* Referral link select */}
                {referrals.length > 0 ? (
                  <ReferralLinkSelect
                    value={selectedUputnica}
                    onChange={setSelectedUputnica}
                    referrals={referrals}
                  />
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-xs"
                    onClick={handleLoadReferrals}
                    disabled={retrieveEUputnice.isPending}
                  >
                    {retrieveEUputnice.isPending && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
                    Učitaj uputnice za povezivanje
                  </Button>
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

      <EReceptDialog
        open={eReceptOpen}
        onOpenChange={setEReceptOpen}
        patientId={patientId}
      />
    </Sheet>
  )
}
