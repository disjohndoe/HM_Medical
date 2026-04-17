"use client"

import { SearchIcon } from "lucide-react"

import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

interface PatientSearchProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
}

export function PatientSearch({
  value,
  onChange,
  placeholder = "Pretraži po imenu, OIB-u, MBO-u, putovnici, EHIC-u...",
  className,
}: PatientSearchProps) {
  return (
    <div className={cn("relative", className)}>
      <SearchIcon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="pl-9"
      />
    </div>
  )
}
