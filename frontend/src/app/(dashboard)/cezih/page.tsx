"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { PageHeader } from "@/components/shared/page-header"
import { CezihStatusCard } from "@/components/cezih/cezih-status"
import { InsuranceCheck } from "@/components/cezih/insurance-check"
import { CezihActivityLog } from "@/components/cezih/activity-log"
import { ForeignerRegistration } from "@/components/cezih/foreigner-registration"
import { usePermissions } from "@/lib/hooks/use-permissions"

export default function CezihPage() {
  const { canViewCezih } = usePermissions()

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

      <Tabs defaultValue="aktivnost" className="space-y-4">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="stranci">Stranci</TabsTrigger>
          <TabsTrigger value="aktivnost">Aktivnost</TabsTrigger>
        </TabsList>

        <TabsContent value="stranci">
          <ForeignerRegistration />
        </TabsContent>

        <TabsContent value="aktivnost">
          <CezihActivityLog />
        </TabsContent>
      </Tabs>
    </div>
  )
}
