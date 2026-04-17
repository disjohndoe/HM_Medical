"use client"

import { useState } from "react"
import { PlusIcon, PencilIcon, EyeIcon, Trash2, Pin } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
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
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { TablePagination } from "@/components/shared/table-pagination"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { BiljeskaForm } from "./biljeska-form"
import { BiljeskaDetail } from "./biljeska-detail"
import { useBiljeske, useDeleteBiljeska } from "@/lib/hooks/use-biljeske"
import { usePermissions } from "@/lib/hooks/use-permissions"
import { BILJESKA_KATEGORIJA, BILJESKA_KATEGORIJA_COLORS } from "@/lib/constants"
import { formatDateHR } from "@/lib/utils"
import type { Biljeska } from "@/lib/types"

const PAGE_SIZE = 20

interface BiljeskaListProps {
  patientId: string
}

export function BiljeskaList({ patientId }: BiljeskaListProps) {
  const [kategorijaFilter, setKategorijaFilter] = useState<string>("")
  const [page, setPage] = useState(0)
  const [formOpen, setFormOpen] = useState(false)
  const [viewBiljeska, setViewBiljeska] = useState<Biljeska | null>(null)
  const [editBiljeska, setEditBiljeska] = useState<Biljeska | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Biljeska | null>(null)

  const { canCreateMedicalRecord, canEditMedicalRecord } = usePermissions()
  const { data, isLoading } = useBiljeske(patientId, kategorijaFilter || undefined, page * PAGE_SIZE, PAGE_SIZE)
  const deleteMutation = useDeleteBiljeska()
  const biljeske = data?.items ?? []

  const { sorted: sortedBiljeske, sortKey: bSortKey, sortDir: bSortDir, toggleSort: toggleBSort } = useTableSort(biljeske, {
    defaultKey: "datum",
    defaultDir: "desc",
    primaryBucket: (b: Biljeska) => (b.is_pinned ? 0 : 1),
    keyAccessors: {
      naslov: (b: Biljeska) => b.naslov,
      kategorija: (b: Biljeska) => BILJESKA_KATEGORIJA[b.kategorija] || b.kategorija,
      doktor: (b: Biljeska) => `${b.doktor_prezime ?? ""} ${b.doktor_ime ?? ""}`.trim(),
    },
  })

  function handleEdit(biljeska: Biljeska) {
    setViewBiljeska(null)
    setEditBiljeska(biljeska)
  }

  function handleDelete() {
    if (!deleteTarget) return
    deleteMutation.mutate(deleteTarget.id, {
      onSuccess: () => {
        toast.success("Bilješka obrisana")
        setDeleteTarget(null)
      },
      onError: (err) => toast.error(err.message),
    })
  }

  if (isLoading) {
    return <LoadingSpinner text="Učitavanje..." />
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <Select value={kategorijaFilter} onValueChange={(v) => { setKategorijaFilter(v ?? ""); setPage(0) }}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Sve kategorije">
              {kategorijaFilter ? BILJESKA_KATEGORIJA[kategorijaFilter] : undefined}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {Object.entries(BILJESKA_KATEGORIJA).map(([slug, label]) => (
              <SelectItem key={slug} value={slug}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {canCreateMedicalRecord && (
          <Button onClick={() => setFormOpen(true)}>
            <PlusIcon className="mr-2 h-4 w-4" />
            Nova bilješka
          </Button>
        )}
      </div>

      {biljeske.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-12">
          <p className="text-muted-foreground">Nema bilješki</p>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <SortableTableHead columnKey="datum" label="Datum" currentKey={bSortKey} currentDir={bSortDir} onSort={toggleBSort} className="w-[100px]" />
              <SortableTableHead columnKey="naslov" label="Naslov" currentKey={bSortKey} currentDir={bSortDir} onSort={toggleBSort} />
              <SortableTableHead columnKey="kategorija" label="Kategorija" currentKey={bSortKey} currentDir={bSortDir} onSort={toggleBSort} className="hidden sm:table-cell" />
              <SortableTableHead columnKey="doktor" label="Doktor" currentKey={bSortKey} currentDir={bSortDir} onSort={toggleBSort} className="hidden lg:table-cell" />
              <TableHead className="text-right">Akcije</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedBiljeske.map((b) => (
              <TableRow key={b.id}>
                <TableCell>
                  <div className="flex items-center gap-1">
                    {b.is_pinned && <Pin className="h-3 w-3 text-amber-500" />}
                    {formatDateHR(b.datum)}
                  </div>
                </TableCell>
                <TableCell className="font-medium">{b.naslov}</TableCell>
                <TableCell className="hidden sm:table-cell">
                  <Badge
                    variant="secondary"
                    className={BILJESKA_KATEGORIJA_COLORS[b.kategorija] || ""}
                  >
                    {BILJESKA_KATEGORIJA[b.kategorija] || b.kategorija}
                  </Badge>
                </TableCell>
                <TableCell className="hidden lg:table-cell">
                  {b.doktor_prezime
                    ? `${b.doktor_ime} ${b.doktor_prezime}`
                    : "—"}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => {
                        setEditBiljeska(null)
                        setViewBiljeska(b)
                      }}
                    >
                      <EyeIcon className="h-4 w-4" />
                    </Button>
                    {canEditMedicalRecord && (
                      <>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onClick={() => handleEdit(b)}
                        >
                          <PencilIcon className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onClick={() => setDeleteTarget(b)}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {data && data.total > 0 && (
        <TablePagination
          page={page}
          pageSize={PAGE_SIZE}
          total={data.total}
          onPageChange={setPage}
        />
      )}

      <BiljeskaForm
        open={formOpen}
        onOpenChange={setFormOpen}
        patientId={patientId}
      />

      <BiljeskaForm
        open={!!editBiljeska}
        onOpenChange={(open) => !open && setEditBiljeska(null)}
        patientId={patientId}
        biljeska={editBiljeska}
      />

      {viewBiljeska && (
        <BiljeskaDetail
          open={!!viewBiljeska}
          onOpenChange={(open) => !open && setViewBiljeska(null)}
          biljeska={viewBiljeska}
          onEdit={() => handleEdit(viewBiljeska)}
        />
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Brisanje bilješke"
        description={`Jeste li sigurni da želite obrisati bilješku "${deleteTarget?.naslov}"? Ova radnja se ne može poništiti.`}
        confirmLabel="Obriši"
        variant="destructive"
        onConfirm={handleDelete}
        loading={deleteMutation.isPending}
      />
    </div>
  )
}
