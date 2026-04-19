"use client"

import { PencilIcon, Pin } from "lucide-react"
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
import { formatDateHR, formatDateTimeHR } from "@/lib/utils"
import { useUpdateBiljeska } from "@/lib/hooks/use-biljeske"
import { usePermissions } from "@/lib/hooks/use-permissions"
import { BILJESKA_KATEGORIJA, BILJESKA_KATEGORIJA_COLORS } from "@/lib/constants"
import type { Biljeska } from "@/lib/types"

interface BiljeskaDetailProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  biljeska: Biljeska
  onEdit: () => void
}

export function BiljeskaDetail({ open, onOpenChange, biljeska, onEdit }: BiljeskaDetailProps) {
  const { canEditMedicalRecord } = usePermissions()
  const updateMutation = useUpdateBiljeska()

  const handleTogglePin = () => {
    updateMutation.mutate(
      { id: biljeska.id, data: { is_pinned: !biljeska.is_pinned } },
      {
        onSuccess: () => toast.success(biljeska.is_pinned ? "Bilješka otkvačena" : "Bilješka prikvačena"),
      },
    )
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="center">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Badge
              variant="secondary"
              className={BILJESKA_KATEGORIJA_COLORS[biljeska.kategorija] || ""}
            >
              {BILJESKA_KATEGORIJA[biljeska.kategorija] || biljeska.kategorija}
            </Badge>
            <span>{formatDateHR(biljeska.datum)}</span>
            {biljeska.is_pinned && <Pin className="h-4 w-4 text-amber-500" />}
          </SheetTitle>
          <SheetDescription>
            {biljeska.doktor_ime
              ? `dr. ${biljeska.doktor_prezime} ${biljeska.doktor_ime}`
              : "—"}
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-4 px-4">
          <div>
            <h4 className="text-sm font-medium text-muted-foreground">Naslov</h4>
            <p className="mt-1 text-sm font-medium">{biljeska.naslov}</p>
          </div>

          <Separator />

          <div>
            <h4 className="text-sm font-medium text-muted-foreground">Sadržaj</h4>
            <div className="mt-1 whitespace-pre-wrap text-sm leading-relaxed">
              {biljeska.sadrzaj}
            </div>
          </div>

          <Separator />

          <div className="text-xs text-muted-foreground">
            Kreirana: {formatDateTimeHR(biljeska.created_at)}
          </div>
          {biljeska.updated_at !== biljeska.created_at && (
            <div className="text-xs text-muted-foreground">
              Zadnja izmjena: {formatDateTimeHR(biljeska.updated_at)}
            </div>
          )}

          {canEditMedicalRecord && (
            <div className="flex gap-2 pt-4">
              <Button variant="outline" className="flex-1" onClick={handleTogglePin}>
                <Pin className="mr-2 h-4 w-4" />
                {biljeska.is_pinned ? "Otkvači" : "Prikvači"}
              </Button>
              <Button variant="outline" className="flex-1" onClick={onEdit}>
                <PencilIcon className="mr-2 h-4 w-4" />
                Uredi
              </Button>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
