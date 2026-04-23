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
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { PageHeader } from "@/components/shared/page-header"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { TablePagination } from "@/components/shared/table-pagination"
import { PatientSearch } from "@/components/patients/patient-search"
import { PatientTable } from "@/components/patients/patient-table"
import { useDeletePatient, usePatients } from "@/lib/hooks/use-patients"
import { useImportPatientByIdentifier, type AdhocIdentifierType } from "@/lib/hooks/use-cezih"
import { usePermissions } from "@/lib/hooks/use-permissions"
import type { Patient } from "@/lib/types"

const PAGE_SIZE = 20

const MBO_REGEX = /^\d{9}$/
const OIB_REGEX = /^\d{11}$/
const PASSPORT_REGEX = /^[A-Za-z0-9]{5,50}$/
const EHIC_REGEX = /^[0-9A-Za-z]{20}$/

export default function PacijentiPage() {
  const [search, setSearch] = useState("")
  const [page, setPage] = useState(0)
  const [deleteTarget, setDeleteTarget] = useState<Patient | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [importType, setImportType] = useState<AdhocIdentifierType>("mbo")
  const [importValue, setImportValue] = useState("")
  const router = useRouter()

  const { data, isLoading, error } = usePatients(search, page * PAGE_SIZE, PAGE_SIZE)
  const deletePatient = useDeletePatient()
  const importPatient = useImportPatientByIdentifier()
  const { canDeletePatient, canPerformCezihOps } = usePermissions()

  function handleDelete(patient: Patient) {
    setDeleteTarget(patient)
  }

  function resetImportDialog() {
    setImportOpen(false)
    setImportType("mbo")
    setImportValue("")
  }

  function handleImportFromCezih() {
    const value = importValue.trim()
    if (importType === "mbo" && !MBO_REGEX.test(value)) {
      toast.error("MBO mora imati točno 9 znamenki")
      return
    }
    if (importType === "oib" && !OIB_REGEX.test(value)) {
      toast.error("OIB mora imati točno 11 znamenki")
      return
    }
    if (importType === "putovnica" && !PASSPORT_REGEX.test(value)) {
      toast.error("Broj putovnice: 5-50 alfanumeričkih znakova")
      return
    }
    if (importType === "ehic" && !EHIC_REGEX.test(value)) {
      toast.error("EHIC broj mora imati točno 20 alfanumeričkih znakova (0-9, A-Z)")
      return
    }
    importPatient.mutate(
      { identifier_type: importType, identifier_value: value },
      {
        onSuccess: (result) => {
          toast.success(
            result.already_exists
              ? `Pacijent ${result.ime} ${result.prezime} već postoji u kartoteci`
              : `Pacijent ${result.ime} ${result.prezime} uspješno kreiran iz CEZIH-a`,
          )
          resetImportDialog()
          router.push(`/pacijenti/${result.id}`)
        },
        onError: (err) => {
          toast.error(err instanceof Error ? err.message : "Greška pri uvozu pacijenta")
        },
      },
    )
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

      <Dialog open={importOpen} onOpenChange={(open) => { if (!open) resetImportDialog() }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Uvoz pacijenta iz CEZIH-a</DialogTitle>
            <DialogDescription>
              Odaberite tip identifikatora i unesite broj za automatsko preuzimanje podataka iz CEZIH registra.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-4">
            <div className="space-y-1.5">
              <Label>Tip identifikatora</Label>
              <Select
                value={importType}
                onValueChange={(v) => {
                  if (!v) return
                  setImportType(v as AdhocIdentifierType)
                  setImportValue("")
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="mbo">MBO</SelectItem>
                  <SelectItem value="oib">OIB</SelectItem>
                  <SelectItem value="putovnica">Putovnica</SelectItem>
                  <SelectItem value="ehic">EHIC kartica</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>
                {importType === "mbo"
                  ? "MBO"
                  : importType === "oib"
                    ? "OIB"
                    : importType === "putovnica"
                      ? "Broj putovnice"
                      : "EHIC broj"}
              </Label>
              <Input
                placeholder={
                  importType === "mbo"
                    ? "MBO (9 znamenki)"
                    : importType === "oib"
                      ? "OIB (11 znamenki)"
                      : importType === "putovnica"
                        ? "AB1234567"
                        : "20 znakova, npr. HR123..."
                }
                value={importValue}
                onChange={(e) => {
                  const raw = e.target.value
                  const isDigitsOnly = importType === "mbo" || importType === "oib"
                  setImportValue(isDigitsOnly ? raw.replace(/\D/g, "") : raw.toUpperCase())
                }}
                maxLength={
                  importType === "mbo"
                    ? 9
                    : importType === "oib"
                      ? 11
                      : importType === "ehic"
                        ? 20
                        : 50
                }
                inputMode={importType === "mbo" || importType === "oib" ? "numeric" : undefined}
                onKeyDown={(e) => { if (e.key === "Enter") handleImportFromCezih() }}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={resetImportDialog}>
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
