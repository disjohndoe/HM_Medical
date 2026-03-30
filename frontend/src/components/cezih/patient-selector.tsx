"use client"

import { useState } from "react"
import { ChevronsUpDown, Check, Search } from "lucide-react"

import { Button } from "@/components/ui/button"
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
import { usePatients } from "@/lib/hooks/use-patients"

export interface SelectedPatient {
  id: string
  name: string
  mbo: string
}

interface PatientSelectorProps {
  value: SelectedPatient | null
  onChange: (patient: SelectedPatient | null) => void
}

export function PatientSelector({ value, onChange }: PatientSelectorProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState("")
  const { data } = usePatients(search.length >= 2 ? search : undefined, 0, 15)
  const patients = data?.items ?? []

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className="w-full justify-between"
          />
        }
      >
        {value ? (
          <span>{value.name} <span className="text-muted-foreground ml-1">MBO: {value.mbo}</span></span>
        ) : (
          <span className="text-muted-foreground">
            <Search className="inline mr-2 h-3 w-3" />
            Odaberite pacijenta...
          </span>
        )}
        <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
      </PopoverTrigger>
      <PopoverContent className="w-[400px] p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput
            placeholder="Pretraži po imenu..."
            value={search}
            onValueChange={setSearch}
          />
          <CommandList>
            <CommandEmpty>
              {search.length < 2 ? "Unesite najmanje 2 znaka" : "Nema rezultata"}
            </CommandEmpty>
            <CommandGroup>
              {patients.map((p) => (
                <CommandItem
                  key={p.id}
                  value={p.id}
                  onSelect={() => {
                    const name = `${p.ime} ${p.prezime}`
                    if (value?.id === p.id) {
                      onChange(null)
                    } else {
                      onChange({ id: p.id, name, mbo: p.mbo || "" })
                    }
                    setOpen(false)
                  }}
                >
                  <Check
                    className={`mr-2 h-4 w-4 ${value?.id === p.id ? "opacity-100" : "opacity-0"}`}
                  />
                  <div className="flex flex-col">
                    <span>{p.ime} {p.prezime}</span>
                    <span className="text-xs text-muted-foreground">
                      MBO: {p.mbo || "—"} | OIB: {p.oib || "—"}
                    </span>
                  </div>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
