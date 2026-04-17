"use client"

import Link from "next/link"
import { PencilIcon, Trash2Icon, EyeIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { SortableTableHead } from "@/components/ui/sortable-table-head"
import { useTableSort } from "@/lib/hooks/use-table-sort"
import type { Patient } from "@/lib/types"
import { formatDateHR } from "@/lib/utils"

interface PatientTableProps {
  patients: Patient[]
  onDelete?: (patient: Patient) => void
}

export function PatientTable({ patients, onDelete }: PatientTableProps) {
  const { sorted, sortKey, sortDir, toggleSort } = useTableSort(patients, {
    defaultKey: "datum_rodjenja",
    defaultDir: "desc",
    keyAccessors: {
      ime_prezime: (p: Patient) => `${p.prezime ?? ""} ${p.ime ?? ""}`.trim(),
      telefon: (p: Patient) => p.mobitel || p.telefon || "",
    },
  })

  if (patients.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-12">
        <p className="text-muted-foreground">Nema pronađenih pacijenata</p>
      </div>
    )
  }

  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <SortableTableHead columnKey="ime_prezime" label="Ime i prezime" currentKey={sortKey} currentDir={sortDir} onSort={toggleSort} />
            <SortableTableHead columnKey="datum_rodjenja" label="Datum rođenja" currentKey={sortKey} currentDir={sortDir} onSort={toggleSort} className="hidden md:table-cell" />
            <SortableTableHead columnKey="oib" label="OIB" currentKey={sortKey} currentDir={sortDir} onSort={toggleSort} className="hidden sm:table-cell" />
            <SortableTableHead columnKey="mbo" label="MBO" currentKey={sortKey} currentDir={sortDir} onSort={toggleSort} className="hidden lg:table-cell" />
            <SortableTableHead columnKey="telefon" label="Telefon" currentKey={sortKey} currentDir={sortDir} onSort={toggleSort} className="hidden lg:table-cell" />
            <TableHead className="w-[100px]">Akcije</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((patient) => (
            <TableRow key={patient.id}>
              <TableCell className="font-medium">
                <div className="flex flex-col">
                  <Link
                    href={`/pacijenti/${patient.id}`}
                    className="hover:underline"
                  >
                    {patient.ime} {patient.prezime}
                  </Link>
                  {patient.spol && (
                    <Badge variant="secondary" className="mt-1 w-fit text-xs">
                      {patient.spol === "M" ? "Muški" : "Ženski"}
                    </Badge>
                  )}
                </div>
              </TableCell>
              <TableCell className="hidden md:table-cell">
                {formatDateHR(patient.datum_rodjenja)}
              </TableCell>
              <TableCell className="hidden sm:table-cell">
                {patient.oib || "—"}
              </TableCell>
              <TableCell className="hidden lg:table-cell">
                {patient.mbo || "—"}
              </TableCell>
              <TableCell className="hidden lg:table-cell">
                {patient.mobitel || patient.telefon || "—"}
              </TableCell>
              <TableCell>
                <div className="flex items-center gap-1">
                  <Button size="icon-xs" variant="ghost" nativeButton={false} render={<Link href={`/pacijenti/${patient.id}`} />}>
                    <EyeIcon className="h-4 w-4" />
                  </Button>
                  <Button size="icon-xs" variant="ghost" nativeButton={false} render={<Link href={`/pacijenti/${patient.id}/uredi`} />}>
                    <PencilIcon className="h-4 w-4" />
                  </Button>
                  {onDelete && (
                    <Button
                      size="icon-xs"
                      variant="ghost"
                      onClick={() => onDelete(patient)}
                    >
                      <Trash2Icon className="h-4 w-4 text-destructive" />
                    </Button>
                  )}
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
