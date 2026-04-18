import { useMutation } from "@tanstack/react-query"
import { toast } from "sonner"

import { api } from "@/lib/api-client"

async function downloadExport(patientId: string, asZip: boolean) {
  const endpoint = asZip
    ? `/patient-rights/${patientId}/export?zip=1`
    : `/patient-rights/${patientId}/export`

  // api.fetchRaw throws on error, no need to check res.ok
  const res = await api.fetchRaw(endpoint)

  // Extract filename from Content-Disposition header
  const disposition = res.headers.get("Content-Disposition") || ""
  let filename = asZip ? "pacijent_podaci.zip" : "pacijent_podaci.json"
  const match = disposition.match(/filename\*?=UTF-8''(.+)|filename="?([^"]+)"?/)
  if (match) {
    filename = decodeURIComponent(match[1] || match[2])
  }

  const blob = await res.blob()

  // Trigger browser download
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function useExportPatientData() {
  return useMutation({
    mutationFn: ({ patientId, asZip = false }: { patientId: string; asZip?: boolean }) =>
      downloadExport(patientId, asZip),
    onError: (err: Error) => { toast.error(err.message) },
  })
}
