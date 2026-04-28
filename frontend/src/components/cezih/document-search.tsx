"use client"

import { useState } from "react"
import {
  Download,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  Users,
  XCircle,
} from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { CezihWaitOverlay } from "@/components/cezih/cezih-wait-overlay"
import { Input } from "@/components/ui/input"
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
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { PatientSelector, type SelectedPatient } from "@/components/cezih/patient-selector"
import {
  useDocumentSearch,
  useRetrieveDocument,
  useReplaceDocument,
  useCancelDocument,
} from "@/lib/hooks/use-cezih"
import { formatDateTimeHR } from "@/lib/utils"

export function DocumentSearch() {
  const [selectedPatient, setSelectedPatient] = useState<SelectedPatient | null>(null)
  const [docType, setDocType] = useState<string>("")
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")
  const [statusFilter, setStatusFilter] = useState<string>("")
  const [cancelTarget, setCancelTarget] = useState<string | null>(null)

  const { data: documents, isLoading, isError, error, refetch } = useDocumentSearch({
    patient_id: selectedPatient?.id || undefined,
    type: docType || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    status: statusFilter || undefined,
  })

  const { sorted: sortedDocs, sortKey: dSortKey, sortDir: dSortDir, toggleSort: toggleDSort } = useTableSort(documents, {
    defaultKey: "datum_izdavanja",
    defaultDir: "desc",
  })

  const retrieveDoc = useRetrieveDocument()
  const replaceDoc = useReplaceDocument()
  const cancelDoc = useCancelDocument()

  const handleRetrieve = (id: string, contentUrl?: string) => {
    retrieveDoc.mutate({ id, contentUrl }, {
      onSuccess: (blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement("a")
        a.href = url
        a.download = `dokument-${id}.pdf`
        a.click()
        URL.revokeObjectURL(url)
        toast.success("Dokument preuzet")
      },
    })
  }

  const handleReplace = (id: string) => {
    replaceDoc.mutate({ referenceId: id }, {
      onSuccess: () => toast.success("Dokument zamijenjen"),
    })
  }

  const handleCancel = () => {
    if (!cancelTarget) return
    cancelDoc.mutate(cancelTarget, {
      onSuccess: () => {
        toast.success("Dokument storniran")
        setCancelTarget(null)
      },
    })
  }

  const hasFilters = selectedPatient?.mbo || docType || dateFrom || dateTo || statusFilter

  return (
    <div className="space-y-4">
      <div className="rounded-md border border-blue-200 bg-blue-50 p-3 text-xs text-blue-900 space-y-1">
        <p className="font-medium">Kako koristiti:</p>
        <ul className="list-disc list-inside space-y-0.5">
          <li>
            <strong>Pretraga</strong> — odaberite pacijenta i filtere (tip, datum, status).
          </li>
          <li>
            <strong>Preuzmi</strong> — skida PDF dokument. <strong>Zamijeni</strong> šalje novu verziju preko CEZIH-a.
            <strong>Storno</strong> poništava dokument. Zamjena i storno zahtijevaju digitalni potpis.
          </li>
        </ul>
      </div>
      {/* Patient selector */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-sm font-medium">Pacijent</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <PatientSelector value={selectedPatient} onChange={setSelectedPatient} />
        </CardContent>
      </Card>

      {/* Search filters */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CardTitle className="text-sm font-medium">Filteri pretrage</CardTitle>
            </div>
            {hasFilters && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setDocType("")
                  setDateFrom("")
                  setDateTo("")
                  setStatusFilter("")
                }}
              >
                <XCircle className="mr-1 h-3 w-3" />
                Očisti filtere
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Select value={docType} onValueChange={(v) => setDocType(v ?? "")}>
              <SelectTrigger>
                <SelectValue placeholder="Tip dokumenta">
                  {{ nalaz: "Nalaz", uputnica: "Uputnica" }[docType] || undefined}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="nalaz">Nalaz</SelectItem>
                <SelectItem value="uputnica">Uputnica</SelectItem>
              </SelectContent>
            </Select>
            <Input
              type="date"
              placeholder="Od datuma"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
            <Input
              type="date"
              placeholder="Do datuma"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
            />
            <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v ?? "")}>
              <SelectTrigger>
                <SelectValue placeholder="Status">
                  {{ current: "Otvorena", superseded: "Zatvorena", "entered-in-error": "Pogreška" }[statusFilter] || undefined}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="current">Otvorena</SelectItem>
                <SelectItem value="superseded">Zatvorena</SelectItem>
                <SelectItem value="entered-in-error">Pogreška</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {!selectedPatient?.mbo ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Search className="h-8 w-8 text-muted-foreground mb-2" />
            <p className="text-sm text-muted-foreground">
              Odaberite pacijenta za pretragu dokumenata
            </p>
          </CardContent>
        </Card>
      ) : isLoading ? (
        <Card>
          <CardContent className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </CardContent>
        </Card>
      ) : isError ? (
        <Card>
          <CardContent className="py-6">
            <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3">
              <p className="text-sm text-destructive">
                Greška pri pretrazi dokumenata: {(error as Error)?.message ?? "Nepoznata greška"}
              </p>
            </div>
          </CardContent>
        </Card>
      ) : !documents || documents.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <p className="text-sm text-muted-foreground">
              Nema pronađenih dokumenata za odabrane filtere
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div className="flex items-center gap-2">
              <CardTitle className="text-lg">Rezultati</CardTitle>
              <Badge variant="outline" className="text-xs">
                {documents.length} dokumenata
              </Badge>
            </div>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              <RefreshCw className="mr-1 h-3 w-3" />
              Osvježi
            </Button>
          </CardHeader>
          <CardContent className="relative">
            <CezihWaitOverlay isOpen={replaceDoc.isPending || cancelDoc.isPending} />
            <Table>
              <TableHeader>
                <TableRow>
                  <SortableTableHead columnKey="id" label="ID" currentKey={dSortKey} currentDir={dSortDir} onSort={toggleDSort} className="hidden sm:table-cell" />
                  <SortableTableHead columnKey="datum_izdavanja" label="Datum" currentKey={dSortKey} currentDir={dSortDir} onSort={toggleDSort} />
                  <SortableTableHead columnKey="svrha" label="Svrha" currentKey={dSortKey} currentDir={dSortDir} onSort={toggleDSort} />
                  <SortableTableHead columnKey="izdavatelj" label="Izdavatelj" currentKey={dSortKey} currentDir={dSortDir} onSort={toggleDSort} className="hidden md:table-cell" />
                  <SortableTableHead columnKey="specijalist" label="Specijalist" currentKey={dSortKey} currentDir={dSortDir} onSort={toggleDSort} className="hidden lg:table-cell" />
                  <SortableTableHead columnKey="status" label="Status" currentKey={dSortKey} currentDir={dSortDir} onSort={toggleDSort} />
                  <TableHead className="text-right">Akcije</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedDocs.map((doc) => (
                  <TableRow key={doc.id}>
                    <TableCell className="hidden sm:table-cell font-mono text-xs">
                      {doc.id}
                    </TableCell>
                    <TableCell className="text-sm">
                      {formatDateTimeHR(doc.datum_izdavanja)}
                    </TableCell>
                    <TableCell className="text-sm max-w-[200px] truncate">
                      {doc.svrha}
                    </TableCell>
                    <TableCell className="hidden md:table-cell text-sm max-w-[200px] truncate">
                      {doc.izdavatelj}
                    </TableCell>
                    <TableCell className="hidden lg:table-cell text-sm max-w-[200px] truncate">
                      {doc.specijalist}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={
                          doc.status === "Zatvorena"
                            ? "bg-green-100 text-green-800 border-green-200"
                            : doc.status === "Pogreška"
                              ? "bg-red-100 text-red-800 border-red-200"
                              : "bg-orange-100 text-orange-800 border-orange-200"
                        }
                      >
                        {doc.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 w-8 p-0"
                          onClick={() => handleRetrieve(doc.id, doc.content_url)}
                          disabled={retrieveDoc.isPending}
                          title="Preuzmi PDF"
                        >
                          <Download className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 w-8 p-0"
                          onClick={() => handleReplace(doc.id)}
                          disabled={replaceDoc.isPending}
                          title="Zamijeni dokument"
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                        </Button>
                        {doc.status !== "Pogreška" && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0 text-destructive hover:text-destructive"
                            onClick={() => setCancelTarget(doc.id)}
                            disabled={cancelDoc.isPending}
                            title="Storno dokument"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Cancel confirmation dialog */}
      <ConfirmDialog
        open={!!cancelTarget}
        onOpenChange={(open: boolean) => !open && setCancelTarget(null)}
        title="Storno dokumenta"
        description={`Jeste li sigurni da želite stornirati dokument ${cancelTarget || ""}? Ova radnja se ne može poništiti.`}
        confirmLabel="Storno"
        variant="destructive"
        onConfirm={handleCancel}
        loading={cancelDoc.isPending}
      />
    </div>
  )
}
