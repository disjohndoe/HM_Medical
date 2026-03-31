"use client"

import { useState } from "react"
import { useParams } from "next/navigation"
import Link from "next/link"
import { PencilIcon, Upload, FileText, Send, PlusIcon, Loader2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { PageHeader } from "@/components/shared/page-header"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { PerformedList } from "@/components/procedures/performed-list"
import { RecordList } from "@/components/medical-records/record-list"
import { DocumentList } from "@/components/documents/document-list"
import { UploadDialog } from "@/components/documents/upload-dialog"
import { PatientCezihTab } from "@/components/cezih/patient-cezih-tab"
import { EkartonView } from "@/components/cezih/ekarton-view"
import { useInsuranceCheck } from "@/lib/hooks/use-cezih"
import { SendNalazDialog } from "@/components/cezih/send-nalaz-dialog"
import { RecordForm } from "@/components/medical-records/record-form"
import { PrescriptionList } from "@/components/prescriptions/prescription-list"
import { usePatient } from "@/lib/hooks/use-patients"
import { usePermissions } from "@/lib/hooks/use-permissions"
import { formatDateHR, formatDateTimeHR } from "@/lib/utils"

export default function PacijentDetailPage() {
  const params = useParams()
  const id = params.id as string
  const { data: patient, isLoading, error } = usePatient(id)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [ekartonState, setEkartonState] = useState<"idle" | "loading" | "loaded">("idle")
  const [ekartonFetchedAt, setEkartonFetchedAt] = useState<string | null>(null)
  const [sendNalazOpen, setSendNalazOpen] = useState(false)
  const [newRecordOpen, setNewRecordOpen] = useState(false)
  const { canViewMedicalRecords, canViewCezih, canViewDocuments, canUploadDocuments, canEditMedicalRecord, canPerformCezihOps } = usePermissions()
  const insuranceCheck = useInsuranceCheck()

  const handleFetchEkarton = () => {
    if (ekartonState === "loaded") {
      setEkartonState("idle")
      setEkartonFetchedAt(null)
      return
    }
    const now = new Date().toISOString()
    setEkartonFetchedAt(now)
    setEkartonState("loading")
    setTimeout(() => {
      setEkartonState("loaded")
      if (patient?.mbo) {
        insuranceCheck.mutate(patient.mbo)
      }
    }, 5000)
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader title="Pacijent" />
        <LoadingSpinner text="Učitavanje..." />
      </div>
    )
  }

  if (error || !patient) {
    return (
      <div className="space-y-6">
        <PageHeader title="Pacijent" />
        <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-4">
          <p className="text-sm text-destructive">
            {error instanceof Error ? error.message : "Pacijent nije pronađen"}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader title={`${patient.ime} ${patient.prezime}`}>
        {canEditMedicalRecord && (
          <Button variant="outline" nativeButton={false} render={<Link href={`/pacijenti/${patient.id}/uredi`} />}>
            <PencilIcon className="mr-2 h-4 w-4" />
            Uredi
          </Button>
        )}
      </PageHeader>

      {/* CEZIH action buttons */}
      {canPerformCezihOps && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Button
              size="lg"
              variant={ekartonState === "loaded" ? "default" : "outline"}
              className="h-12 text-base"
              onClick={handleFetchEkarton}
              disabled={ekartonState === "loading"}
            >
              {ekartonState === "loading" ? (
                <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              ) : (
                <FileText className="mr-2 h-5 w-5" />
              )}
              {ekartonState === "loading"
                ? "Dohvaćanje podataka sa CEZIH poslužitelja..."
                : ekartonState === "loaded"
                  ? "Sakrij e-Karton"
                  : "Dohvati e-Karton"}
            </Button>
            <Button
              size="lg"
              variant="outline"
              className="h-12 text-base"
              onClick={() => setNewRecordOpen(true)}
            >
              <PlusIcon className="mr-2 h-5 w-5" />
              Novi nalaz
            </Button>
            <Button
              size="lg"
              className="h-12 text-base bg-emerald-600 hover:bg-emerald-700 text-white"
              onClick={() => setSendNalazOpen(true)}
            >
              <Send className="mr-2 h-5 w-5" />
              Pošalji nalaze (CEZIH)
            </Button>
          </div>
          {ekartonState === "loaded" && (
            <EkartonView
              patientId={id}
              patientMbo={patient.mbo}
              alergije={patient.alergije}
              fetchTime={ekartonFetchedAt}
            />
          )}
        </div>
      )}

      <Tabs defaultValue="pregled">
        <TabsList>
          <TabsTrigger value="pregled">Pregled</TabsTrigger>
          <TabsTrigger value="postupci">Postupci</TabsTrigger>
          {canViewMedicalRecords && <TabsTrigger value="nalazi">Nalazi</TabsTrigger>}
          {canPerformCezihOps && <TabsTrigger value="recepti">Recepti</TabsTrigger>}
          {canViewDocuments && <TabsTrigger value="dokumenti">Dokumenti</TabsTrigger>}
          {canViewCezih && <TabsTrigger value="cezih">CEZIH</TabsTrigger>}
        </TabsList>

        <TabsContent value="pregled" className="space-y-4">
          {/* Osobni podaci */}
          <Card>
            <CardHeader>
              <CardTitle>Osobni podaci</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <div>
                  <dt className="text-sm text-muted-foreground">Ime i prezime</dt>
                  <dd className="font-medium">
                    {patient.ime} {patient.prezime}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-muted-foreground">Datum rođenja</dt>
                  <dd className="font-medium">{formatDateHR(patient.datum_rodjenja)}</dd>
                </div>
                <div>
                  <dt className="text-sm text-muted-foreground">Spol</dt>
                  <dd className="font-medium">
                    {patient.spol === "M" ? "Muški" : patient.spol === "Z" ? "Ženski" : "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-muted-foreground">OIB</dt>
                  <dd className="font-medium">{patient.oib || "—"}</dd>
                </div>
                <div>
                  <dt className="text-sm text-muted-foreground">MBO</dt>
                  <dd className="font-medium">{patient.mbo || "—"}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>

          {/* Kontakt podaci */}
          <Card>
            <CardHeader>
              <CardTitle>Kontakt podaci</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <div>
                  <dt className="text-sm text-muted-foreground">Adresa</dt>
                  <dd className="font-medium">
                    {patient.adresa || "—"}
                    {patient.grad && `, ${patient.grad}`}
                    {patient.postanski_broj && ` ${patient.postanski_broj}`}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-muted-foreground">Telefon</dt>
                  <dd className="font-medium">{patient.telefon || "—"}</dd>
                </div>
                <div>
                  <dt className="text-sm text-muted-foreground">Mobitel</dt>
                  <dd className="font-medium">{patient.mobitel || "—"}</dd>
                </div>
                <div>
                  <dt className="text-sm text-muted-foreground">Email</dt>
                  <dd className="font-medium">{patient.email || "—"}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>

          {/* Medicinski podaci */}
          <Card>
            <CardHeader>
              <CardTitle>Medicinski podaci</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <dt className="text-sm text-muted-foreground">Alergije</dt>
                <dd className="mt-1 font-medium">{patient.alergije || "Nema zabilježenih alergija"}</dd>
              </div>
              <Separator />
              <div>
                <dt className="text-sm text-muted-foreground">Napomena</dt>
                <dd className="mt-1 font-medium">{patient.napomena || "Nema napomena"}</dd>
              </div>
            </CardContent>
          </Card>

          {/* Metapodaci */}
          <Card>
            <CardHeader>
              <CardTitle>Metapodaci</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-3 sm:grid-cols-2">
                <div>
                  <dt className="text-sm text-muted-foreground">Kreiran</dt>
                  <dd className="font-medium">{formatDateTimeHR(patient.created_at)}</dd>
                </div>
                <div>
                  <dt className="text-sm text-muted-foreground">Zadnja izmjena</dt>
                  <dd className="font-medium">{formatDateTimeHR(patient.updated_at)}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="postupci">
          <PerformedList patientId={id} />
        </TabsContent>

        {canViewMedicalRecords && (
          <TabsContent value="nalazi">
            <RecordList patientId={id} />
          </TabsContent>
        )}

        {canPerformCezihOps && (
          <TabsContent value="recepti">
            <PrescriptionList patientId={id} />
          </TabsContent>
        )}

        {canViewDocuments && (
          <TabsContent value="dokumenti" className="space-y-4">
            <div className="flex justify-end">
              {canUploadDocuments && (
                <Button onClick={() => setUploadOpen(true)}>
                  <Upload className="mr-2 h-4 w-4" />
                  Upload dokument
                </Button>
              )}
            </div>
            <DocumentList patientId={id} />
            <UploadDialog
              open={uploadOpen}
              onOpenChange={setUploadOpen}
              patientId={id}
            />
          </TabsContent>
        )}

        {canViewCezih && (
          <TabsContent value="cezih">
            <PatientCezihTab patientId={id} patientMbo={patient.mbo} />
          </TabsContent>
        )}
      </Tabs>

      <RecordForm
        open={newRecordOpen}
        onOpenChange={setNewRecordOpen}
        patientId={id}
      />

      <SendNalazDialog
        open={sendNalazOpen}
        onOpenChange={setSendNalazOpen}
        patientId={id}
      />
    </div>
  )
}
