"use client"

import { useParams } from "next/navigation"
import { PageHeader } from "@/components/shared/page-header"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { PatientForm } from "@/components/patients/patient-form"
import { usePatient, useUpdatePatient } from "@/lib/hooks/use-patients"

export default function UrediPacijentaPage() {
  const params = useParams()
  const id = params.id as string
  const { data: patient, isLoading, error } = usePatient(id)
  const updatePatient = useUpdatePatient()

  async function handleSubmit(data: Parameters<typeof updatePatient.mutateAsync>[0]["data"]) {
    await updatePatient.mutateAsync({ id, data })
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader title="Uredi pacijenta" />
        <LoadingSpinner text="Učitavanje..." />
      </div>
    )
  }

  if (error || !patient) {
    return (
      <div className="space-y-6">
        <PageHeader title="Uredi pacijenta" />
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
      <PageHeader
        title={`Uredi: ${patient.ime} ${patient.prezime}`}
        description="Ažurirajte podatke o pacijentu"
      />
      <PatientForm
        patient={patient}
        onSubmit={handleSubmit}
        isSubmitting={updatePatient.isPending}
      />
    </div>
  )
}
