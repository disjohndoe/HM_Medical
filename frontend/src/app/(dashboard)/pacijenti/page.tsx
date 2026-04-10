"use client"

import { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { PlusIcon, Download, Loader2 } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { PageHeader } from "@/components/shared/page-header"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { TablePagination } from "@/components/shared/table-pagination"
import { PatientSearch } from "@/components/patients/patient-search"
import { PatientTable } from "@/components/patients/patient-table"
import { useDeletePatient, usePatients } from "@/lib/hooks/use-patients"
import { useImportPatientFromCezih } from "@/lib/hooks/use-cezih"
import { usePermissions } from "@/lib/hooks/use-permissions"
import type { Patient } from "@/lib/types"

const PAGE_SIZE = 20

export default function PacijentiPage() {
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(0)
  const [deleteTarget, setDeleteTarget] = useState<Patient | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [importMbo, setImportMbo] = useState("")
  const router = useRouter()

  const { data, isLoading, error } = usePatients(search, page * PAGE_SIZE, PAGE_SIZE)
  const deletePatient = useDeletePatient()
  const importPatient = useImportPatientFromCezih()
  const { canDeletePatient, canPerformCezihOps } = usePermissions()

  function handleDelete(patient: Patient) {
    setDeleteTarget(patient)
  }

  function handleImportFromCezih() {
    const mbo = importMbo.trim()
    if (!/^\d{9}$/.test(mbo)) {
      toast.error("MBO mora imati točno 9 znamenki")
      return
    }
    importPatient.mutate(mbo, {
      onSuccess: (result) => {
        toast.success(`Pacijent ${result.ime} ${result.prezime} uspješno kreiran iz CEZIH-a`)
        setImportOpen(false)
        setImportMbo("")
        router.push(`/pacijenti/${result.id}`)
      },
      onError: (err) => {
        toast.error(err instanceof Error ? err.message : "Greška pri uvozu pacijenta")
      },
    })
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
        {canPerformCezihOps && (
          <Button
            variant="outline"
            className="bg-sky-500 hover:bg-sky-600 text-white border-sky-500"
            onClick={() => setImportOpen(true)}
          >
            <Download className="mr-2 h-4 w-4" />
            Uvoz iz CEZIH-a
          </Button>
        )}
        <Button nativeButton={false} render={<Link href="/pacijenti/novi" />}>
          <PlusIcon className="mr-2 h-4 w-4" />
          Novi pacijent
        </Button>
      </PageHeader>

      <PatientSearch value={search} onChange={(v) => { setSearch(v); setPage(0) }} />

      {isLoading ? (
        <LoadingSpinner text="Učitavanje pacijenata..." />
      ) : (
        <>
          <PatientTable
            patients={data?.items ?? []}
            onDelete={canDeletePatient ? handleDelete : undefined}
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

      <Dialog open={importOpen} onOpenChange={(open) => { if (!open) { setImportOpen(false); setImportMbo("") } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Uvoz pacijenta iz CEZIH-a</DialogTitle>
            <DialogDescription>
              Unesite MBO pacijenta za automatsko preuzimanje podataka iz CEZIH registra.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Input
              placeholder="MBO (9 znamenki)"
              value={importMbo}
              onChange={(e) => setImportMbo(e.target.value)}
              maxLength={9}
              onKeyDown={(e) => { if (e.key === "Enter") handleImportFromCezih() }}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setImportOpen(false); setImportMbo("") }}>
              Odustani
            </Button>
            <Button
              onClick={handleImportFromCezih}
              disabled={importPatient.isPending}
              className="bg-sky-500 hover:bg-sky-600 text-white"
            >
              {importPatient.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Dohvati iz CEZIH-a
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
