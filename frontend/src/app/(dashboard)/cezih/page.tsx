"use client"

import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { PageHeader } from "@/components/shared/page-header"
import { CezihStatusCard } from "@/components/cezih/cezih-status"
import { InsuranceCheck } from "@/components/cezih/insurance-check"
import { CezihActivityLog } from "@/components/cezih/activity-log"
import { ForeignerRegistration } from "@/components/cezih/foreigner-registration"
import { RegistryTools } from "@/components/cezih/registry-tools"
import { usePermissions } from "@/lib/hooks/use-permissions"
import { useCezihStatus as useSettingsCezihStatus, useGenerateAgentSecret } from "@/lib/hooks/use-settings"

export default function CezihPage() {
  const { canViewCezih } = usePermissions()
  const { data: settingsStatus } = useSettingsCezihStatus()
  const generateSecret = useGenerateAgentSecret()
  const [generatedSecret, setGeneratedSecret] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const handleGenerate = async () => {
    try {
      const res = await generateSecret.mutateAsync()
      setGeneratedSecret(res.agent_secret)
      setCopied(false)
      await navigator.clipboard.writeText(res.agent_secret)
      setCopied(true)
    } catch {
      // mutation error handled by react-query
    }
  }

  const handleCopy = async () => {
    if (generatedSecret) {
      await navigator.clipboard.writeText(generatedSecret)
      setCopied(true)
    }
  }

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
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="stranci">Stranci</TabsTrigger>
          <TabsTrigger value="registri">Registri</TabsTrigger>
          <TabsTrigger value="aktivnost">Aktivnost</TabsTrigger>
          <TabsTrigger value="postavke">Postavke</TabsTrigger>
        </TabsList>

        <TabsContent value="stranci">
          <ForeignerRegistration />
        </TabsContent>

        <TabsContent value="registri">
          <RegistryTools />
        </TabsContent>

        <TabsContent value="aktivnost">
          <CezihActivityLog />
        </TabsContent>

        <TabsContent value="postavke">
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Konfiguracija</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <p className="text-sm text-muted-foreground">Šifra ustanove</p>
                    <p className="text-sm font-medium">
                      {settingsStatus?.sifra_ustanove || "Nije postavljena"}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">OID</p>
                    <p className="text-sm font-mono">
                      {settingsStatus?.oid || "Nije postavljen"}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">Status:</span>
                  <Badge variant="secondary">
                    {settingsStatus?.status || "Nepovezano"}
                  </Badge>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Lokalni agent</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-block h-2.5 w-2.5 rounded-full ${
                      settingsStatus?.agent_connected
                        ? "bg-green-500"
                        : "bg-muted-foreground/50"
                    }`}
                  />
                  <span className="text-sm">
                    {settingsStatus?.agent_connected
                      ? "Agent je povezan"
                      : "Agent nije povezan"}
                  </span>
                </div>
                {settingsStatus?.last_heartbeat && (
                  <p className="text-xs text-muted-foreground">
                    Zadnji heartbeat: {new Date(settingsStatus.last_heartbeat).toLocaleString("hr-HR")}
                  </p>
                )}

                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={handleGenerate}
                      disabled={generateSecret.isPending}
                    >
                      {generateSecret.isPending ? "Generiranje..." : "Generiraj tajni ključ"}
                    </Button>
                    {generatedSecret && (
                      <Button size="sm" variant="ghost" onClick={handleCopy}>
                        {copied ? "Kopirano!" : "Kopiraj"}
                      </Button>
                    )}
                  </div>

                  {generatedSecret && (
                    <div className="rounded-md bg-muted p-3">
                      <p className="mb-1 text-xs font-medium text-muted-foreground">Tajni ključ agenta:</p>
                      <code className="block break-all text-xs">{generatedSecret}</code>
                    </div>
                  )}

                  <div className="rounded-md border p-3">
                    <p className="mb-2 text-sm font-medium">Upute za postavljanje</p>
                    <ol className="list-inside list-decimal space-y-1 text-sm text-muted-foreground">
                      <li>Generirajte tajni ključ gore</li>
                      <li>Preuzmite i instalirajte HM Digital Agent aplikaciju</li>
                      <li>Postavite okružne varijable:
                        <code className="ml-1 rounded bg-muted px-1 text-xs">HM_TENANT_ID</code> i
                        <code className="ml-1 rounded bg-muted px-1 text-xs">HM_AGENT_SECRET</code>
                      </li>
                      <li>Pokrenite agent — status povezanosti prikazat će se ovdje</li>
                    </ol>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
