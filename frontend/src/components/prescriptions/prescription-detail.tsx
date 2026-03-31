"use client"

import { useState } from "react"
import { Loader2, Send, XCircle, Trash2 } from "lucide-react"
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { MockBadge } from "@/components/cezih/mock-badge"
import { useSendPrescription, useStornoPrescription, useDeletePrescription } from "@/lib/hooks/use-prescriptions"
import { usePermissions } from "@/lib/hooks/use-permissions"
import { formatDateTimeHR } from "@/lib/utils"
import type { Prescription } from "@/lib/types"

interface PrescriptionDetailProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  prescription: Prescription
}

function statusBadge(p: Prescription) {
  if (p.cezih_storno) return <Badge className="bg-red-100 text-red-800 border-red-200">Storniran</Badge>
  if (p.cezih_sent) return <Badge className="bg-green-100 text-green-800 border-green-200">Poslan</Badge>
  return <Badge variant="outline">Nacrt</Badge>
}

export function PrescriptionDetail({ open, onOpenChange, prescription }: PrescriptionDetailProps) {
  const sendPrescription = useSendPrescription()
  const stornoPrescription = useStornoPrescription()
  const deletePrescription = useDeletePrescription()
  const { canUseHzzo } = usePermissions()
  const [confirmStorno, setConfirmStorno] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const handleSend = () => {
    sendPrescription.mutate(prescription.id, {
      onSuccess: (res) => toast.success(`e-Recept poslan (${res.cezih_recept_id})`),
      onError: (err) => toast.error(err.message),
    })
  }

  const handleStorno = () => {
    stornoPrescription.mutate(prescription.id, {
      onSuccess: () => {
        toast.success("e-Recept storniran")
        setConfirmStorno(false)
      },
      onError: (err) => toast.error(err.message),
    })
  }

  const handleDelete = () => {
    deletePrescription.mutate(prescription.id, {
      onSuccess: () => {
        toast.success("Nacrt recepta obrisan")
        setConfirmDelete(false)
        onOpenChange(false)
      },
      onError: (err) => toast.error(err.message),
    })
  }

  const isDraft = !prescription.cezih_sent
  const isSent = prescription.cezih_sent && !prescription.cezih_storno
  const isStorniran = prescription.cezih_storno

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="center">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            {statusBadge(prescription)}
            <MockBadge />
          </SheetTitle>
          <SheetDescription>
            {prescription.doktor_ime
              ? `dr. ${prescription.doktor_prezime} ${prescription.doktor_ime}`
              : "—"}
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-4 px-4">
          {/* CEZIH info */}
          {prescription.cezih_recept_id && (
            <div>
              <h4 className="text-sm font-medium text-muted-foreground">CEZIH referenca</h4>
              <p className="mt-1 font-mono text-sm">{prescription.cezih_recept_id}</p>
              {prescription.cezih_sent_at && (
                <p className="text-xs text-muted-foreground">
                  Poslano: {formatDateTimeHR(prescription.cezih_sent_at)}
                </p>
              )}
              {prescription.cezih_storno_at && (
                <p className="text-xs text-muted-foreground">
                  Stornirano: {formatDateTimeHR(prescription.cezih_storno_at)}
                </p>
              )}
            </div>
          )}

          {prescription.cezih_recept_id && <Separator />}

          {/* Drugs table */}
          <div>
            <h4 className="text-sm font-medium text-muted-foreground">Lijekovi</h4>
            <Table className="mt-2">
              <TableHeader>
                <TableRow>
                  <TableHead>Naziv</TableHead>
                  <TableHead className="hidden sm:table-cell">Oblik</TableHead>
                  <TableHead>Kol.</TableHead>
                  <TableHead>Doziranje</TableHead>
                  <TableHead className="hidden md:table-cell">Napomena</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {prescription.lijekovi.map((lijek, i) => (
                  <TableRow key={i}>
                    <TableCell className="text-sm font-medium">
                      {lijek.naziv}
                      {lijek.jacina && (
                        <span className="ml-1 text-xs text-muted-foreground">{lijek.jacina}</span>
                      )}
                    </TableCell>
                    <TableCell className="hidden sm:table-cell text-xs text-muted-foreground">
                      {lijek.oblik || "—"}
                    </TableCell>
                    <TableCell className="text-sm">{lijek.kolicina}</TableCell>
                    <TableCell className="text-sm">{lijek.doziranje || "—"}</TableCell>
                    <TableCell className="hidden md:table-cell text-xs text-muted-foreground">
                      {lijek.napomena || "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {prescription.napomena && (
            <>
              <Separator />
              <div>
                <h4 className="text-sm font-medium text-muted-foreground">Napomena</h4>
                <p className="mt-1 text-sm">{prescription.napomena}</p>
              </div>
            </>
          )}

          <Separator />

          {/* Actions */}
          <div className="flex gap-2">
            {isDraft && (
              <>
                {canUseHzzo && (
                  <Button
                    size="sm"
                    onClick={handleSend}
                    disabled={sendPrescription.isPending}
                  >
                    {sendPrescription.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Send className="mr-2 h-4 w-4" />
                    )}
                    Pošalji na CEZIH
                  </Button>
                )}
                <Button
                  variant="outline"
                  size="sm"
                  className="text-destructive hover:text-destructive"
                  onClick={() => setConfirmDelete(true)}
                  disabled={deletePrescription.isPending}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  Obriši
                </Button>
              </>
            )}
            {isSent && canUseHzzo && (
              <Button
                variant="outline"
                size="sm"
                className="text-destructive hover:text-destructive"
                onClick={() => setConfirmStorno(true)}
                disabled={stornoPrescription.isPending}
              >
                {stornoPrescription.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <XCircle className="mr-2 h-4 w-4" />
                )}
                Storniraj
              </Button>
            )}
          </div>

          <div className="text-xs text-muted-foreground">
            Kreiran: {formatDateTimeHR(prescription.created_at)}
          </div>
        </div>
      </SheetContent>

      <ConfirmDialog
        open={confirmStorno}
        onOpenChange={setConfirmStorno}
        title="Storno e-Recepta"
        description="Jeste li sigurni da želite stornirati ovaj e-Recept? Ova radnja se ne može poništiti."
        confirmLabel="Storniraj"
        variant="destructive"
        onConfirm={handleStorno}
        loading={stornoPrescription.isPending}
      />

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Brisanje nacrta"
        description="Jeste li sigurni da želite obrisati ovaj nacrt recepta?"
        confirmLabel="Obriši"
        variant="destructive"
        onConfirm={handleDelete}
        loading={deletePrescription.isPending}
      />
    </Sheet>
  )
}
