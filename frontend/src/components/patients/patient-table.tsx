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
import type { Patient } from "@/lib/types"
import { formatDateHR } from "@/lib/utils"

interface PatientTableProps {
  patients: Patient[]
  onDelete?: (patient: Patient) => void
}

export function PatientTable({ patients, onDelete }: PatientTableProps) {
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
            <TableHead>Ime i prezime</TableHead>
            <TableHead className="hidden md:table-cell">Datum rođenja</TableHead>
            <TableHead className="hidden sm:table-cell">OIB</TableHead>
            <TableHead className="hidden lg:table-cell">MBO</TableHead>
            <TableHead className="hidden lg:table-cell">Telefon</TableHead>
            <TableHead className="w-[100px]">Akcije</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {patients.map((patient) => (
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
