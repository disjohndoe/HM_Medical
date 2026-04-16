"use client"

import { useState, useEffect, useRef } from "react"
import { useSearchParams } from "next/navigation"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { PageHeader } from "@/components/shared/page-header"
import { CezihStatusCard } from "@/components/cezih/cezih-status"
import { InsuranceCheck } from "@/components/cezih/insurance-check"
import { CezihActivityLog } from "@/components/cezih/activity-log"
import { ForeignerRegistration } from "@/components/cezih/foreigner-registration"
import { RegistryTools } from "@/components/cezih/registry-tools"
import { toast } from "sonner"
import { CreditCard, X, Loader2 } from "lucide-react"
import { useAuth } from "@/lib/auth"
import { usePermissions } from "@/lib/hooks/use-permissions"
import { useSettingsCezihStatus, useGenerateAgentSecret, useCreatePairingToken } from "@/lib/hooks/use-settings"
import { useCezihStatus } from "@/lib/hooks/use-cezih"
import { useSelfBindCard, useSelfUnbindCard } from "@/lib/hooks/use-users"

const VALID_TABS = ["stranci", "registri", "aktivnost", "postavke"]

export default function CezihPage() {
  const searchParams = useSearchParams()
  const tabParam = searchParams.get("tab")
  const defaultTab = tabParam && VALID_TABS.includes(tabParam) ? tabParam : "aktivnost"
  const { user, refreshUser } = useAuth()
  const { canViewCezih } = usePermissions()
  const isAdmin = user?.role === "admin"
  const { data: settingsStatus } = useSettingsCezihStatus(isAdmin)
  const { data: cezihStatus } = useCezihStatus()
  const selfBind = useSelfBindCard()
  const selfUnbind = useSelfUnbindCard()
  const generateSecret = useGenerateAgentSecret()
  const createPairingToken = useCreatePairingToken()
  const [generatedSecret, setGeneratedSecret] = useState<string | null>(null)
  const [generatedTenantId, setGeneratedTenantId] = useState<string | null>(null)
  const [copied, setCopied] = useState<string | null>(null)
  const [pairingFallback, setPairingFallback] = useState(false)

  useEffect(() => {
    if (cezihStatus?.agent_connected) {
      setGeneratedSecret(null)
      setGeneratedTenantId(null)
      setPairingFallback(false)
    }
  }, [cezihStatus?.agent_connected])

  const handleGenerate = async () => {
    try {
      const res = await generateSecret.mutateAsync()
      setGeneratedSecret(res.agent_secret)
      setGeneratedTenantId(res.tenant_id)
    } catch {
      // mutation error handled by react-query
    }
  }

  const handleCopy = async (text: string, key: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(key)
      setTimeout(() => setCopied(null), 2000)
    } catch {
      toast.error("Kopiranje nije uspjelo. Pokušajte ručno označiti tekst.")
    }
  }

  const handlePairAgent = async () => {
    setPairingFallback(false)
    try {
      if (!generatedSecret) {
        const res = await generateSecret.mutateAsync()
        setGeneratedSecret(res.agent_secret)
        setGeneratedTenantId(res.tenant_id)
      }
      const pairRes = await createPairingToken.mutateAsync()
      window.location.href = pairRes.pairing_url
      setTimeout(() => setPairingFallback(true), 3000)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Greška pri povezivanju agenta")
    }
  }

  // Suppression is keyed by the card holder that last failed to auto-bind.
  // A different card (holder changed) or the same card after the user clicks
  // "Pokušaj ponovno" clears suppression and attempts auto-bind again.
  const [suppressedHolder, setSuppressedHolder] = useState<string | null>(null)
  const suppressAutoBind =
    suppressedHolder !== null && suppressedHolder === (cezihStatus?.card_holder ?? null)

  // Guard against double-fire of auto-bind mutation
  const bindingInFlight = useRef(false)

  // Auto-bind card when detected and user has no binding
  useEffect(() => {
    if (
      !user?.card_holder_name &&
      cezihStatus?.agent_connected &&
      cezihStatus?.card_inserted &&
      cezihStatus?.card_holder &&
      !selfBind.isPending &&
      !suppressAutoBind &&
      !bindingInFlight.current
    ) {
      bindingInFlight.current = true
      selfBind.mutate(undefined, {
        onSuccess: () => {
          bindingInFlight.current = false
          toast.success("Kartica automatski povezana s vašim računom")
          refreshUser()
        },
        onError: (err) => {
          bindingInFlight.current = false
          setSuppressedHolder(cezihStatus?.card_holder ?? "")
          toast.error(err instanceof Error ? err.message : "Automatsko povezivanje kartice nije uspjelo")
        },
      })
    }
  }, [user?.card_holder_name, cezihStatus?.agent_connected, cezihStatus?.card_inserted, cezihStatus?.card_holder, selfBind.isPending, suppressAutoBind])

  const handleManualBind = () => {
    bindingInFlight.current = true
    setSuppressedHolder(null)
    selfBind.mutate(undefined, {
      onSuccess: () => {
        bindingInFlight.current = false
        toast.success("Kartica povezana s vašim računom")
        refreshUser()
      },
      onError: (err) => {
        bindingInFlight.current = false
        setSuppressedHolder(cezihStatus?.card_holder ?? "")
        toast.error(err instanceof Error ? err.message : "Povezivanje kartice nije uspjelo")
      },
    })
  }

  const handleSelfUnbind = () => {
    setSuppressedHolder(cezihStatus?.card_holder ?? "")
    selfUnbind.mutate(undefined, {
      onSuccess: () => {
        toast.success("Kartica odpojena")
        refreshUser()
      },
      onError: (err) => {
        setSuppressedHolder(null)
        toast.error(err instanceof Error ? err.message : "Greška pri odpajanju kartice")
      },
    })
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

      <Tabs defaultValue={defaultTab} className="space-y-4">
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
                <CardTitle className="flex items-center gap-2 text-lg">
                  <CreditCard className="h-5 w-5" />
                  AKD Kartica
                </CardTitle>
              </CardHeader>
              <CardContent>
                {user?.card_holder_name ? (
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">{user.card_holder_name}</p>
                      <p className="text-xs text-muted-foreground">Kartica je povezana s vašim računom</p>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleSelfUnbind}
                      disabled={selfUnbind.isPending}
                    >
                      {selfUnbind.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <X className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    {selfBind.isPending ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                        <p className="text-sm text-muted-foreground">Povezivanje kartice...</p>
                      </>
                    ) : suppressAutoBind ? (
                      <div className="flex items-center gap-2">
                        <p className="text-sm text-red-600">
                          Automatsko povezivanje nije uspjelo.
                        </p>
                        {cezihStatus?.agent_connected && cezihStatus?.card_inserted && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={handleManualBind}
                            disabled={selfBind.isPending}
                          >
                            {selfBind.isPending ? (
                              <Loader2 className="h-4 w-4 animate-spin mr-1" />
                            ) : null}
                            Pokušaj ponovno
                          </Button>
                        )}
                      </div>
                    ) : (
                      <p className="text-sm text-muted-foreground">
                        {!cezihStatus?.agent_connected
                          ? "Čeka se povezivanje agenta..."
                          : !cezihStatus?.card_inserted
                            ? "Umetnite AKD karticu u čitač"
                            : "Detektirana kartica, povezivanje..."}
                      </p>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            {isAdmin && (
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
                </CardContent>
              </Card>
            )}

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Lokalni agent</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-block h-2.5 w-2.5 rounded-full ${
                      cezihStatus?.agent_connected
                        ? "bg-green-500"
                        : "bg-muted-foreground/50"
                    }`}
                  />
                  <span className="text-sm">
                    {cezihStatus?.agent_connected
                      ? "Agent je povezan"
                      : "Agent nije povezan"}
                  </span>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={handleGenerate}
                      disabled={generateSecret.isPending || cezihStatus?.agent_connected}
                    >
                      {generateSecret.isPending
                        ? "Generiranje..."
                        : cezihStatus?.agent_connected
                          ? "Agent je već povezan"
                          : "Generiraj pristupne podatke"}
                    </Button>
                    {generatedSecret && !cezihStatus?.agent_connected && (
                      <Button
                        size="sm"
                        onClick={handlePairAgent}
                        disabled={createPairingToken.isPending}
                      >
                        {createPairingToken.isPending ? "Povezivanje..." : "Poveži agenta"}
                      </Button>
                    )}
                  </div>

                  {pairingFallback && (
                    <p className="text-xs text-amber-600">
                      Agent se nije pokrenuo? Provjerite je li <strong>HM Digital Agent</strong> instaliran na ovom računalu.
                    </p>
                  )}

                  {generatedSecret && generatedTenantId && (
                    <div className="rounded-md bg-muted p-3 space-y-2">
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <p className="text-xs font-medium text-muted-foreground">Tenant ID</p>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-5 text-xs px-1"
                            onClick={() => handleCopy(generatedTenantId, "tenant")}
                          >
                            {copied === "tenant" ? "Kopirano!" : "Kopiraj"}
                          </Button>
                        </div>
                        <code className="block break-all text-xs">{generatedTenantId}</code>
                      </div>
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <p className="text-xs font-medium text-muted-foreground">Tajni ključ</p>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-5 text-xs px-1"
                            onClick={() => handleCopy(generatedSecret, "secret")}
                          >
                            {copied === "secret" ? "Kopirano!" : "Kopiraj"}
                          </Button>
                        </div>
                        <code className="block break-all text-xs">{generatedSecret}</code>
                      </div>
                    </div>
                  )}

                  <div className="rounded-md border p-3">
                    <p className="mb-2 text-sm font-medium">Upute za postavljanje</p>
                    <ol className="list-inside list-decimal space-y-1 text-sm text-muted-foreground">
                      <li>Kliknite <strong>"Generiraj pristupne podatke"</strong> — dobit ćete Tenant ID i tajni ključ</li>
                      <li>Instalirajte <strong>HM Digital Agent</strong> na računalo u ordinaciji</li>
                      <li>Kliknite <strong>"Poveži agenta"</strong> — agent će se automatski konfigurirati</li>
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
