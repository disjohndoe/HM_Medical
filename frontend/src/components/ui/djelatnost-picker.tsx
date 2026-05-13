"use client"

import { useMemo, useState } from "react"
import { Check, ChevronsUpDown } from "lucide-react"

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
import { cn } from "@/lib/utils"
import {
  SIFRANIK_DJELATNOSTI,
  SIFRANIK_DJELATNOSTI_BY_CODE,
} from "@/lib/sifranik-djelatnosti"

export interface DjelatnostPickerProps {
  code: string | null
  onChange: (code: string | null, display: string | null) => void
  placeholder?: string
  disabled?: boolean
  className?: string
}

export function DjelatnostPicker({
  code,
  onChange,
  placeholder = "Odaberite šifru djelatnosti",
  disabled,
  className,
}: DjelatnostPickerProps) {
  const [open, setOpen] = useState(false)

  const selected = useMemo(() => {
    if (!code) return null
    return SIFRANIK_DJELATNOSTI_BY_CODE.get(code) ?? null
  }, [code])

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            disabled={disabled}
            className={cn("w-full justify-between", className)}
          />
        }
      >
        {selected ? (
          <span className="flex items-center gap-2 truncate">
            <span className="font-mono text-xs">{selected.code}</span>
            <span className="truncate">{selected.name}</span>
          </span>
        ) : (
          <span className="text-muted-foreground">{placeholder}</span>
        )}
        <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] min-w-[420px] p-0" align="start">
        <Command
          filter={(value, search) => {
            const q = search.trim().toLowerCase()
            if (!q) return 1
            return value.toLowerCase().includes(q) ? 1 : 0
          }}
        >
          <CommandInput placeholder="Pretraži po šifri ili nazivu..." />
          <CommandList>
            <CommandEmpty>Nema rezultata.</CommandEmpty>
            <CommandGroup>
              {SIFRANIK_DJELATNOSTI.map((entry) => (
                <CommandItem
                  key={entry.code}
                  value={`${entry.code} ${entry.name}`}
                  onSelect={() => {
                    if (entry.code === code) {
                      onChange(null, null)
                    } else {
                      onChange(entry.code, entry.name)
                    }
                    setOpen(false)
                  }}
                >
                  <Check
                    className={cn(
                      "mr-2 h-4 w-4",
                      entry.code === code ? "opacity-100" : "opacity-0",
                    )}
                  />
                  <span className="font-mono text-xs text-muted-foreground mr-2 shrink-0">
                    {entry.code}
                  </span>
                  <span className="truncate">{entry.name}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
