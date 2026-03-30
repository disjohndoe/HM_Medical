"use client"

import { useState } from "react"
import Link from "next/link"
import { PlusIcon } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { PageHeader } from "@/components/shared/page-header"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { PatientSearch } from "@/components/patients/patient-search"
import { PatientTable } from "@/components/patients/patient-table"
import { useDeletePatient, usePatients } from "@/lib/hooks/use-patients"
import { usePermissions } from "@/lib/hooks/use-permissions"
import type { Patient } from "@/lib/types"

export default function PacijentiPage() {
  const [search, setSearch] = useState("")
  const [deleteTarget, setDeleteTarget] = useState<Patient | null>(null)

  const { data, isLoading, error } = usePatients(search)
  const deletePatient = useDeletePatient()
  const { canDeletePatient } = usePermissions()

  function handleDelete(patient: Patient) {
    setDeleteTarget(patient)
  }

  async function confirmDelete() {
    if (!deleteTarget) return
    try {
      await deletePatient.mutateAsync(deleteTarget.id)
      toast.success("Pacijent izbrisan")
      setDeleteTarget(null)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Greška pri brisanju")
    }
  }

  if (error) {
    return (
      <div className="space-y-6">
        <PageHeader title="Pacijenti" description="Upravljanje pacijentima" />
        <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-4">
          <p className="text-sm text-destructive">
            {error instanceof Error ? error.message : "Greška pri učitavanju"}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Pacijenti" description="Upravljanje pacijentima">
        <Button nativeButton={false} render={<Link href="/pacijenti/novi" />}>
          <PlusIcon className="mr-2 h-4 w-4" />
          Novi pacijent
        </Button>
      </PageHeader>

      <PatientSearch value={search} onChange={setSearch} />

      {isLoading ? (
        <LoadingSpinner text="Učitavanje pacijenata..." />
      ) : (
        <>
          <PatientTable
            patients={data?.items ?? []}
            onDelete={canDeletePatient ? handleDelete : undefined}
          />
          {data && data.total > 0 && (
            <p className="text-sm text-muted-foreground">
              Ukupno {data.total} pacijenata
            </p>
          )}
        </>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title="Brisanje pacijenta"
        description={`Jeste li sigurni da želite obrisati pacijenta ${deleteTarget?.ime} ${deleteTarget?.prezime}?`}
        confirmLabel="Obriši"
        variant="destructive"
        onConfirm={confirmDelete}
        loading={deletePatient.isPending}
      />
    </div>
  )
}
