"use client"

import { useEffect, useState } from "react"
import { Loader2, Plus, Trash2, Search } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { useDrugSearch } from "@/lib/hooks/use-cezih"
import {
  useCreatePrescription,
  useSendPrescription,
  useUpdatePrescription,
} from "@/lib/hooks/use-prescriptions"
import { usePermissions } from "@/lib/hooks/use-permissions"
import type { LijekItem, Prescription } from "@/lib/types"

interface SelectedDrug {
  atk: string
  naziv: string
  oblik: string
  jacina: string
  kolicina: number
  doziranje: string
  napomena: string
}

interface PrescriptionFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  patientId: string
  prescription?: Prescription | null
}

export function PrescriptionForm({ open, onOpenChange, patientId, prescription }: PrescriptionFormProps) {
  const isEdit = !!prescription
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [selected, setSelected] = useState<SelectedDrug[]>([])
  const [napomena, setNapomena] = useState("")
  const { data: drugs } = useDrugSearch(searchQuery)
  const createPrescription = useCreatePrescription()
  const updatePrescription = useUpdatePrescription()
  const sendPrescription = useSendPrescription()
  const { canUseHzzo } = usePermissions()

  useEffect(() => {
    if (open) {
      if (prescription) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setSelected(
          prescription.lijekovi.map((l) => ({
            atk: l.atk,
            naziv: l.naziv,
            oblik: l.oblik,
            jacina: l.jacina,
            kolicina: l.kolicina,
            doziranje: l.doziranje,
            napomena: l.napomena,
          })),
        )
         
        setNapomena(prescription.napomena ?? "")
      } else {
         
        setSelected([])
         
        setNapomena("")
      }
      setSearchQuery("")
    }
  }, [open, prescription])

  const handleAddDrug = (drug: LijekItem) => {
    if (selected.some((s) => s.atk === drug.atk && s.naziv === drug.naziv && s.oblik === drug.oblik && s.jacina === drug.jacina)) {
      toast.info("Lijek je već dodan")
      return
    }
    setSelected((prev) => [
      ...prev,
      {
        atk: drug.atk,
        naziv: drug.naziv,
        oblik: drug.oblik,
        jacina: drug.jacina,
        kolicina: 1,
        doziranje: "",
        napomena: "",
      },
    ])
    setSearchOpen(false)
    setSearchQuery("")
  }

  const handleRemoveDrug = (index: number) => {
    setSelected((prev) => prev.filter((_, i) => i !== index))
  }

  const handleUpdateDrug = (index: number, field: keyof SelectedDrug, value: string | number) => {
    setSelected((prev) =>
      prev.map((drug, i) => (i === index ? { ...drug, [field]: value } : drug))
    )
  }

  const resetAndClose = () => {
    setSelected([])
    setNapomena("")
    setSearchQuery("")
    onOpenChange(false)
  }

  const handleSave = (andSend: boolean) => {
    if (selected.length === 0) {
      toast.error("Dodajte barem jedan lijek")
      return
    }

    if (isEdit && prescription) {
      updatePrescription.mutate(
        {
          id: prescription.id,
          data: {
            lijekovi: selected.map((d) => ({
              atk: d.atk,
              naziv: d.naziv,
              oblik: d.oblik,
              jacina: d.jacina,
              kolicina: d.kolicina,
              doziranje: d.doziranje,
              napomena: d.napomena,
            })),
            napomena: napomena || null,
          },
        },
        {
          onSuccess: (updated) => {
            if (andSend) {
              sendPrescription.mutate(updated.id, {
                onSuccess: (res) => {
                  toast.success(`e-Recept poslan (${res.cezih_recept_id})`)
                  resetAndClose()
                },
                onError: (err) => toast.error(err.message),
              })
            } else {
              toast.success("Recept ažuriran")
              resetAndClose()
            }
          },
          onError: (err) => toast.error(err.message),
        },
      )
      return
    }

    createPrescription.mutate(
      {
        patient_id: patientId,
        lijekovi: selected.map((d) => ({
          atk: d.atk,
          naziv: d.naziv,
          oblik: d.oblik,
          jacina: d.jacina,
          kolicina: d.kolicina,
          doziranje: d.doziranje,
          napomena: d.napomena,
        })),
        napomena: napomena || null,
      },
      {
        onSuccess: (created) => {
          if (andSend) {
            sendPrescription.mutate(created.id, {
              onSuccess: (res) => {
                toast.success(`e-Recept poslan (${res.cezih_recept_id})`)
                resetAndClose()
              },
              onError: (err) => toast.error(err.message),
            })
          } else {
            toast.success("Recept spremljen kao nacrt")
            resetAndClose()
          }
        },
        onError: (err) => toast.error(err.message),
      },
    )
  }

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      setSelected([])
      setNapomena("")
      setSearchQuery("")
    }
    onOpenChange(open)
  }

  const isPending =
    createPrescription.isPending || updatePrescription.isPending || sendPrescription.isPending

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <DialogTitle>{isEdit ? "Uredi recept" : "Novi recept"}</DialogTitle>
          </div>
        </DialogHeader>

        <div className="space-y-4">
          {/* Drug search */}
          <Popover open={searchOpen} onOpenChange={setSearchOpen}>
            <PopoverTrigger
              render={<Button variant="outline" className="w-full justify-start text-muted-foreground" />}
            >
              <Search className="mr-2 h-4 w-4" />
              Pretraži lijekove...
            </PopoverTrigger>
            <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
              <Command shouldFilter={false}>
                <CommandInput
                  placeholder="Naziv ili ATK šifra..."
                  value={searchQuery}
                  onValueChange={setSearchQuery}
                />
                <CommandList>
                  <CommandEmpty>
                    {searchQuery.length < 2 ? "Unesite barem 2 znaka" : "Nema rezultata"}
                  </CommandEmpty>
                  <CommandGroup>
                    {drugs?.map((drug) => (
                      <CommandItem
                        key={`${drug.atk}-${drug.naziv}-${drug.oblik}-${drug.jacina}`}
                        value={drug.naziv}
                        onSelect={() => handleAddDrug(drug)}
                      >
                        <Plus className="mr-2 h-3 w-3" />
                        <div className="flex-1">
                          <p className="text-sm">{drug.naziv}</p>
                          <p className="text-xs text-muted-foreground">
                            {drug.oblik || drug.jacina} · ATK: {drug.atk}
                          </p>
                        </div>
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>

          {/* Selected drugs table */}
          {selected.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Naziv</TableHead>
                  <TableHead className="hidden sm:table-cell">Oblik</TableHead>
                  <TableHead className="w-20">Kol.</TableHead>
                  <TableHead className="w-32">Doziranje</TableHead>
                  <TableHead className="hidden md:table-cell w-32">Napomena</TableHead>
                  <TableHead className="w-10"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {selected.map((drug, index) => (
                  <TableRow key={index}>
                    <TableCell className="text-sm font-medium">{drug.naziv}</TableCell>
                    <TableCell className="hidden sm:table-cell text-xs text-muted-foreground">
                      {drug.oblik}
                    </TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        min={1}
                        value={drug.kolicina}
                        onChange={(e) => handleUpdateDrug(index, "kolicina", parseInt(e.target.value) || 1)}
                        className="h-8 w-16"
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        placeholder="npr. 1-0-1"
                        value={drug.doziranje}
                        onChange={(e) => handleUpdateDrug(index, "doziranje", e.target.value)}
                        className="h-8"
                      />
                    </TableCell>
                    <TableCell className="hidden md:table-cell">
                      <Input
                        placeholder="Napomena"
                        value={drug.napomena}
                        onChange={(e) => handleUpdateDrug(index, "napomena", e.target.value)}
                        className="h-8"
                      />
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemoveDrug(index)}
                        className="h-8 w-8 p-0"
                      >
                        <Trash2 className="h-3 w-3 text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {/* Napomena */}
          <div>
            <label className="text-sm font-medium">Napomena (opcionalno)</label>
            <Textarea
              placeholder="Dodatne napomene za recept..."
              value={napomena}
              onChange={(e) => setNapomena(e.target.value)}
              className="mt-1"
              rows={2}
            />
          </div>
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Odustani
          </Button>
          <Button
            variant="secondary"
            onClick={() => handleSave(false)}
            disabled={isPending || selected.length === 0}
          >
            {isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {isEdit ? "Spremi promjene" : "Spremi nacrt"}
          </Button>
          {canUseHzzo && (
            <Button
              onClick={() => handleSave(true)}
              disabled={isPending || selected.length === 0}
            >
              {isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {isEdit ? "Spremi i pošalji" : "Spremi i pošalji"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
