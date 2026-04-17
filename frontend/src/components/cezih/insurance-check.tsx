import { useState } from "react"
import { Search, Loader2 } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { useInsuranceCheckByMbo } from "@/lib/hooks/use-cezih"
import { OSIGURANJE_STATUS } from "@/lib/constants"
import { formatDateHR } from "@/lib/utils"

export function InsuranceCheck() {
  const [mbo, setMbo] = useState("")
  const checkInsurance = useInsuranceCheckByMbo()

  const handleCheck = () => {
    if (!mbo || mbo.length !== 9 || !/^\d{9}$/.test(mbo)) {
      toast.error("MBO mora imati točno 9 znamenki")
      return
    }
    checkInsurance.mutate(mbo, {
      onError: (err) => toast.error(err.message),
    })
  }

  const result = checkInsurance.data
  const statusInfo = result ? OSIGURANJE_STATUS[result.status_osiguranja] : null

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-lg">Provjera osiguranja</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          <Input
            placeholder="MBO (9 znamenki)"
            value={mbo}
            onChange={(e) => setMbo(e.target.value.replace(/\D/g, "").slice(0, 9))}
            maxLength={9}
            onKeyDown={(e) => e.key === "Enter" && handleCheck()}
          />
          <Button
            onClick={handleCheck}
            disabled={checkInsurance.isPending || mbo.length !== 9}
          >
            {checkInsurance.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Search className="mr-2 h-4 w-4" />
            )}
            Provjeri
          </Button>
        </div>

        {result && (
          <>
            <Separator />
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{result.ime} {result.prezime}</span>
                {statusInfo && (
                  <Badge variant="secondary" className={statusInfo.color}>
                    {statusInfo.label}
                  </Badge>
                )}
              </div>
              <div className="grid gap-2 text-sm sm:grid-cols-2">
                <div>
                  <span className="text-muted-foreground">MBO:</span>{" "}
                  <span className="font-mono">{result.mbo}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">OIB:</span>{" "}
                  <span className="font-mono">{result.oib}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Datum rođenja:</span>{" "}
                  {formatDateHR(result.datum_rodjenja)}
                </div>
                <div>
                  <span className="text-muted-foreground">Spol:</span>{" "}
                  {result.spol}
                </div>
                <div>
                  <span className="text-muted-foreground">Osiguravatelj:</span>{" "}
                  {result.osiguravatelj}
                </div>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
