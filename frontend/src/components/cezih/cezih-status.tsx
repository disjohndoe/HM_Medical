import { CreditCard } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { useCezihConnectionDisplay } from "@/lib/hooks/use-cezih"
import { useCardStatus } from "@/lib/hooks/use-users"
import { useAuth } from "@/lib/auth"
import { MockBadge } from "./mock-badge"

export function CezihStatusCard() {
  const cezih = useCezihConnectionDisplay()
  const { data: cardStatus } = useCardStatus()
  const { user } = useAuth()

  const isMyCard = cardStatus?.matched_doctor_id === user?.id

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-lg">Status veze</CardTitle>
        {cezih.isDemo && <MockBadge />}
      </CardHeader>
      <CardContent>
        {cezih.isLoading ? (
          <div className="text-sm text-muted-foreground">Učitavanje...</div>
        ) : cezih.raw ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className={`inline-block h-2.5 w-2.5 rounded-full ${cezih.dotColor}`} />
              <span className="text-sm">{cezih.label}</span>
            </div>
            {cezih.connectedDoctor && (
              <div className="text-sm text-muted-foreground">
                {cezih.connectedDoctor}
                {cezih.connectedClinic && <> via {cezih.connectedClinic}</>}
              </div>
            )}
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Način:</span>
              <Badge variant={cezih.isDemo ? "destructive" : "outline"} className={cezih.isDemo ? "uppercase font-bold" : ""}>
                {cezih.isDemo ? "DEMO" : cezih.raw.mode}
              </Badge>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Agent:</span>
              <span className="text-sm">
                {cezih.raw.agent_connected ? "Povezan" : "Nije povezan"}
              </span>
            </div>

            <div className="border-t pt-3 space-y-2">
              <div className="flex items-center gap-2">
                <CreditCard className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm text-muted-foreground">AKD Kartica:</span>
                {cardStatus?.card_inserted ? (
                  <Badge variant="outline" className="gap-1">
                    {cardStatus.card_holder ?? "Nepoznato"}
                  </Badge>
                ) : (
                  <span className="text-sm">Nije umetnuta</span>
                )}
              </div>
              {cardStatus?.card_inserted && cardStatus?.matched_doctor_name && (
                <div className="flex items-center gap-2 pl-6">
                  <span
                    className={`inline-block h-2 w-2 rounded-full ${
                      isMyCard ? "bg-green-500" : "bg-orange-500"
                    }`}
                  />
                  <span className="text-sm">
                    {isMyCard
                      ? "Vaša kartica"
                      : `Kartica: ${cardStatus.matched_doctor_name}`}
                  </span>
                </div>
              )}
              {cardStatus?.card_inserted && !cardStatus?.matched_doctor_name && (
                <div className="flex items-center gap-2 pl-6">
                  <span className="inline-block h-2 w-2 rounded-full bg-red-500" />
                  <span className="text-sm text-muted-foreground">
                    Kartica nije povezana s korisnikom
                  </span>
                </div>
              )}
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
