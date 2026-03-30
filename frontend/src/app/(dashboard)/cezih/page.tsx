"use client"

import { useState } from "react"
import { Download, Loader2, Users } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { PageHeader } from "@/components/shared/page-header"
import { formatDateHR } from "@/lib/utils"
import { CezihStatusCard } from "@/components/cezih/cezih-status"
import { InsuranceCheck } from "@/components/cezih/insurance-check"
import { MockBadge } from "@/components/cezih/mock-badge"
import { CezihActivityLog } from "@/components/cezih/activity-log"
import { VisitManagement } from "@/components/cezih/visit-management"
import { CaseManagement } from "@/components/cezih/case-management"
import { ForeignerRegistration } from "@/components/cezih/foreigner-registration"
import { DocumentSearch } from "@/components/cezih/document-search"
import { PatientSelector, type SelectedPatient } from "@/components/cezih/patient-selector"
import { useRetrieveEUputnice, useEUputnice } from "@/lib/hooks/use-cezih"
import { usePermissions } from "@/lib/hooks/use-permissions"

export default function CezihPage() {
  const { canViewCezih } = usePermissions()
  const retrieveEUputnice = useRetrieveEUputnice()
  const { data: storedEUputnice } = useEUputnice()
  const [selectedPatient, setSelectedPatient] = useState<SelectedPatient | null>(null)

  const handleRetrieveEUputnice = () => {
    retrieveEUputnice.mutate(undefined, {
      onSuccess: () => toast.success("e-Uputnice dohvaćene"),
      onError: (err) => toast.error(err.message),
    })
  }

  const euputnice = storedEUputnice?.items ?? []

  if (!canViewCezih) {
    return (
      <div className="space-y-6">
        <PageHeader title="CEZIH" />
        <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-4">
          <p className="text-sm text-destructive">Nemate pristup ovoj stranici.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader title="CEZIH" />

      <div className="grid gap-6 lg:grid-cols-2">
        <CezihStatusCard />
        <InsuranceCheck />
      </div>

      <Tabs defaultValue="uputnice" className="space-y-4">
        <TabsList className="grid w-full grid-cols-6">
          <TabsTrigger value="uputnice">e-Uputnice</TabsTrigger>
          <TabsTrigger value="posjete">Posjete</TabsTrigger>
          <TabsTrigger value="slucajevi">Slučajevi</TabsTrigger>
          <TabsTrigger value="dokumenti">Dokumenti</TabsTrigger>
          <TabsTrigger value="stranci">Stranci</TabsTrigger>
          <TabsTrigger value="aktivnost">Aktivnost</TabsTrigger>
        </TabsList>

        <TabsContent value="uputnice">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div className="flex items-center gap-2">
                <CardTitle className="text-lg">e-Uputnice</CardTitle>
                <MockBadge />
              </div>
              <Button
                onClick={handleRetrieveEUputnice}
                disabled={retrieveEUputnice.isPending}
              >
                {retrieveEUputnice.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Download className="mr-2 h-4 w-4" />
                )}
                Dohvati e-Uputnice
              </Button>
            </CardHeader>
            <CardContent>
              {euputnice.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8">
                  <p className="text-sm text-muted-foreground">
                    Kliknite &quot;Dohvati e-Uputnice&quot; za prikaz primljenih uputnica
                  </p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="hidden sm:table-cell">ID</TableHead>
                      <TableHead>Datum</TableHead>
                      <TableHead>Svrha</TableHead>
                      <TableHead className="hidden md:table-cell">Izdavatelj</TableHead>
                      <TableHead className="hidden lg:table-cell">Specijalist</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {euputnice.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell className="hidden sm:table-cell font-mono text-xs">{item.id}</TableCell>
                        <TableCell>{formatDateHR(item.datum_izdavanja)}</TableCell>
                        <TableCell>{item.svrha}</TableCell>
                        <TableCell className="hidden md:table-cell max-w-[200px] truncate">{item.izdavatelj}</TableCell>
                        <TableCell className="hidden lg:table-cell max-w-[200px] truncate">{item.specijalist}</TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={
                              item.status === "Zatvorena"
                                ? "bg-green-100 text-green-800 border-green-200"
                                : "bg-orange-100 text-orange-800 border-orange-200"
                            }
                          >
                            {item.status}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="posjete">
          <Card className="mb-4">
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
          {selectedPatient?.mbo ? (
            <VisitManagement patientId={selectedPatient.id} patientMbo={selectedPatient.mbo} />
          ) : (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <Users className="h-8 w-8 text-muted-foreground mb-2" />
                <p className="text-sm text-muted-foreground">
                  Odaberite pacijenta za upravljanje posjetama
                </p>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="slucajevi">
          <Card className="mb-4">
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
          {selectedPatient?.mbo ? (
            <CaseManagement patientId={selectedPatient.id} patientMbo={selectedPatient.mbo} />
          ) : (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <Users className="h-8 w-8 text-muted-foreground mb-2" />
                <p className="text-sm text-muted-foreground">
                  Odaberite pacijenta za upravljanje slučajevima
                </p>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="stranci">
          <ForeignerRegistration />
        </TabsContent>

        <TabsContent value="dokumenti">
          <DocumentSearch />
        </TabsContent>

        <TabsContent value="aktivnost">
          <CezihActivityLog />
        </TabsContent>
      </Tabs>
    </div>
  )
}
