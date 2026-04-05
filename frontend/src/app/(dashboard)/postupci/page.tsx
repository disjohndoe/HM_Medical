"use client"

import { useState } from "react"
import { PlusIcon, SearchIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { PageHeader } from "@/components/shared/page-header"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { TablePagination } from "@/components/shared/table-pagination"
import { ProcedureTable } from "@/components/procedures/procedure-table"
import { ProcedureForm } from "@/components/procedures/procedure-form"
import { useProcedures, useDeleteProcedure } from "@/lib/hooks/use-procedures"
import { usePermissions } from "@/lib/hooks/use-permissions"
import { PROCEDURE_KATEGORIJA_OPTIONS } from "@/lib/constants"
import type { Procedure } from "@/lib/types"

const PAGE_SIZE = 20

export default function PostupciPage() {
  const [search, setSearch] = useState("")
  const [kategorija, setKategorija] = useState<string>("")
  const [page, setPage] = useState(0)
  const [formOpen, setFormOpen] = useState(false)
  const [editingProcedure, setEditingProcedure] = useState<Procedure | undefined>()
  const [deleteTarget, setDeleteTarget] = useState<Procedure | null>(null)

  const { data, isLoading } = useProcedures(
    kategorija || undefined,
    search || undefined,
    page * PAGE_SIZE,
    PAGE_SIZE,
  )
  const deleteMutation = useDeleteProcedure()
  const { canCreateProcedure, canEditProcedure, canDeleteProcedure } = usePermissions()

  function handleEdit(procedure: Procedure) {
    setEditingProcedure(procedure)
    setFormOpen(true)
  }

  function handleCreate() {
    setEditingProcedure(undefined)
    setFormOpen(true)
  }

  async function handleDelete() {
    if (!deleteTarget) return
    try {
      await deleteMutation.mutateAsync(deleteTarget.id)
      setDeleteTarget(null)
    } catch {
      // Error handled by toast in mutation
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Katalog postupaka" description="Upravljanje katalogom medicinskih postupaka">
        {canCreateProcedure && (
          <Button onClick={handleCreate}>
            <PlusIcon className="mr-2 h-4 w-4" />
            Novi postupak
          </Button>
        )}
      </PageHeader>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <SearchIcon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Pretraži po šifri, nazivu ili opisu..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0) }}
            className="pl-9"
          />
        </div>
        <Select value={kategorija} onValueChange={(v) => { setKategorija(v ?? ""); setPage(0) }}>
          <SelectTrigger className="w-full sm:w-[200px]">
            <SelectValue placeholder="Sve kategorije">
              {kategorija ? PROCEDURE_KATEGORIJA_OPTIONS.find((o) => o.value === kategorija)?.label : undefined}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {PROCEDURE_KATEGORIJA_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <LoadingSpinner text="Učitavanje postupaka..." />
      ) : (
        <>
          <ProcedureTable
            procedures={data?.items ?? []}
            onEdit={canEditProcedure ? handleEdit : undefined}
            onDelete={canDeleteProcedure ? setDeleteTarget : undefined}
          />
          {data && data.total > 0 && (
            <TablePagination
              page={page}
              pageSize={PAGE_SIZE}
              total={data.total}
              onPageChange={setPage}
            />
          )}
        </>
      )}

      <ProcedureForm
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open)
          if (!open) setEditingProcedure(undefined)
        }}
        procedure={editingProcedure}
      />

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Obriši postupak"
        description={`Jeste li sigurni da želite obrisati postupak "${deleteTarget?.naziv}"?`}
        onConfirm={handleDelete}
        loading={deleteMutation.isPending}
        variant="destructive"
        confirmLabel="Obriši"
      />
    </div>
  )
}
