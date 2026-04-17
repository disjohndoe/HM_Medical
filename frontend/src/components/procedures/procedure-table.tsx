"use client"

import { PencilIcon, TrashIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
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
import { PROCEDURE_KATEGORIJA } from "@/lib/constants"
import { formatCurrencyEUR } from "@/lib/utils"
import type { Procedure } from "@/lib/types"

interface ProcedureTableProps {
  procedures: Procedure[]
  onEdit?: (procedure: Procedure) => void
  onDelete?: (procedure: Procedure) => void
}

export function ProcedureTable({ procedures, onEdit, onDelete }: ProcedureTableProps) {
  const { sorted, sortKey, sortDir, toggleSort } = useTableSort(procedures, {
    defaultKey: "naziv",
    defaultDir: "asc",
    keyAccessors: {
      kategorija: (p: Procedure) => PROCEDURE_KATEGORIJA[p.kategorija] || p.kategorija,
      cijena: (p: Procedure) => p.cijena_cents,
      trajanje: (p: Procedure) => p.trajanje_minuta,
    },
  })

  if (procedures.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-12">
        <p className="text-muted-foreground">Nema pronađenih postupaka</p>
      </div>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <SortableTableHead columnKey="sifra" label="Šifra" currentKey={sortKey} currentDir={sortDir} onSort={toggleSort} />
          <SortableTableHead columnKey="naziv" label="Naziv" currentKey={sortKey} currentDir={sortDir} onSort={toggleSort} />
          <SortableTableHead columnKey="kategorija" label="Kategorija" currentKey={sortKey} currentDir={sortDir} onSort={toggleSort} className="hidden md:table-cell" />
          <SortableTableHead columnKey="cijena" label="Cijena" currentKey={sortKey} currentDir={sortDir} onSort={toggleSort} className="hidden sm:table-cell text-right" />
          <SortableTableHead columnKey="trajanje" label="Trajanje" currentKey={sortKey} currentDir={sortDir} onSort={toggleSort} className="hidden lg:table-cell text-right" />
          <TableHead className="hidden md:table-cell">Status</TableHead>
          <TableHead className="text-right">Akcije</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((p) => (
          <TableRow key={p.id}>
            <TableCell className="font-mono text-xs">{p.sifra}</TableCell>
            <TableCell className="font-medium">{p.naziv}</TableCell>
            <TableCell className="hidden md:table-cell">
              {PROCEDURE_KATEGORIJA[p.kategorija] || p.kategorija}
            </TableCell>
            <TableCell className="hidden sm:table-cell text-right">
              {formatCurrencyEUR(p.cijena_cents / 100)}
            </TableCell>
            <TableCell className="hidden lg:table-cell text-right">
              {p.trajanje_minuta} min
            </TableCell>
            <TableCell className="hidden md:table-cell">
              <Badge variant="default" className="bg-green-100 text-green-800">
                Aktivan
              </Badge>
            </TableCell>
            <TableCell className="text-right">
              <div className="flex justify-end gap-1">
                {onEdit && (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => onEdit(p)}
                  >
                    <PencilIcon className="h-4 w-4" />
                  </Button>
                )}
                {onDelete && (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => onDelete(p)}
                  >
                    <TrashIcon className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
