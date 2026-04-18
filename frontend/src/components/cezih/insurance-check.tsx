import { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Search, Loader2, UserPlus, ExternalLink } from "lucide-react"
import { toast } from "sonner"

import { Button, buttonVariants } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  useInsuranceCheckByIdentifier,
  useImportPatientByIdentifier,
  type AdhocIdentifierType,
} from "@/lib/hooks/use-cezih"
import { OSIGURANJE_STATUS } from "@/lib/constants"
import { formatDateHR } from "@/lib/utils"

type IdType = AdhocIdentifierType

const ID_CONFIG: Record<IdType, {
  label: string
  placeholder: string
  validate: (v: string) => boolean
  errorMsg: string
  sanitize?: (v: string) => string
}> = {
  mbo: {
    label: "MBO",
    placeholder: "MBO (9 znamenki)",
    validate: (v) => /^\d{9}$/.test(v),
    errorMsg: "MBO mora imati točno 9 znamenki",
    sanitize: (v) => v.replace(/\D/g, "").slice(0, 9),
  },
  ehic: {
    label: "EHIC",
    placeholder: "EHIC broj (20 znakova)",
    validate: (v) => /^[0-9A-Za-z]{20}$/.test(v),
    errorMsg: "EHIC broj mora imati točno 20 alfanumeričkih znakova",
    sanitize: (v) => v.replace(/[^0-9A-Za-z]/g, "").slice(0, 20),
  },
  putovnica: {
    label: "Putovnica",
    placeholder: "Broj putovnice (5-15 znakova)",
    validate: (v) => /^[A-Za-z0-9]{5,15}$/.test(v),
    errorMsg: "Broj putovnice mora imati 5-15 alfanumeričkih znakova",
    sanitize: (v) => v.replace(/[^A-Za-z0-9]/g, "").slice(0, 15),
  },
}

export function InsuranceCheck() {
  const router = useRouter()
  const [idType, setIdType] = useState<IdType>("mbo")
  const [value, setValue] = useState("")
  const checkInsurance = useInsuranceCheckByIdentifier()
  const importPatient = useImportPatientByIdentifier()
  const [importedId, setImportedId] = useState<string | null>(null)

  const config = ID_CONFIG[idType]

  const handleCheck = () => {
    if (!config.validate(value)) {
      toast.error(config.errorMsg)
      return
    }
    setImportedId(null)
    importPatient.reset()
    checkInsurance.mutate(
      { identifier_type: idType, identifier_value: value },
      { onError: (err) => toast.error(err.message) },
    )
  }

  const handleTypeChange = (v: IdType | null) => {
    if (!v) return
    setIdType(v)
    setValue("")
    checkInsurance.reset()
    importPatient.reset()
    setImportedId(null)
  }

  const result = checkInsurance.data
  const statusInfo = result ? OSIGURANJE_STATUS[result.status_osiguranja] : null
  const submittedType: IdType = checkInsurance.variables?.identifier_type ?? "mbo"
  const submittedValue = checkInsurance.variables?.identifier_value ?? ""
  const submittedLabel = ID_CONFIG[submittedType].label

  const handleImport = () => {
    if (!submittedValue) return
    importPatient.mutate(
      { identifier_type: submittedType, identifier_value: submittedValue },
      {
        onSuccess: (data) => {
          setImportedId(data.id)
          toast.success(
            data.already_exists
              ? "Pacijent već postoji u kartoteci — otvorite postojeći karton."
              : "Pacijent dodan u kartoteku.",
          )
        },
        onError: (err) => toast.error(err.message),
      },
    )
  }

  const resultHasPatient = !!result && !!result.ime && result.status_osiguranja !== "Nije pronađen"
  const isDeceased = !!result?.datum_smrti

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-lg">Provjera osiguranja</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          <Select value={idType} onValueChange={handleTypeChange}>
            <SelectTrigger className="w-[130px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="mbo">MBO</SelectItem>
              <SelectItem value="ehic">EHIC</SelectItem>
              <SelectItem value="putovnica">Putovnica</SelectItem>
            </SelectContent>
          </Select>
          <Input
            placeholder={config.placeholder}
            value={value}
            onChange={(e) => setValue(config.sanitize ? config.sanitize(e.target.value) : e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCheck()}
          />
          <Button
            onClick={handleCheck}
            disabled={checkInsurance.isPending || !config.validate(value)}
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
                {result.mbo && (
                  <div>
                    <span className="text-muted-foreground">{submittedLabel}:</span>{" "}
                    <span className="font-mono">{result.mbo}</span>
                  </div>
                )}
                {result.oib && (
                  <div>
                    <span className="text-muted-foreground">OIB:</span>{" "}
                    <span className="font-mono">{result.oib}</span>
                  </div>
                )}
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
                {isDeceased && (
                  <div>
                    <span className="text-muted-foreground">Datum smrti:</span>{" "}
                    <span className="text-destructive font-medium">{formatDateHR(result.datum_smrti!)}</span>
                  </div>
                )}
              </div>

              {resultHasPatient && !isDeceased && (
                <div className="flex items-center gap-2 pt-1">
                  {importedId ? (
                    <Link
                      href={`/pacijenti/${importedId}`}
                      className={buttonVariants({ variant: "outline", size: "sm" })}
                    >
                      <ExternalLink className="mr-2 h-4 w-4" />
                      Otvori karton
                    </Link>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={handleImport}
                      disabled={importPatient.isPending}
                    >
                      {importPatient.isPending ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <UserPlus className="mr-2 h-4 w-4" />
                      )}
                      Dodaj u kartoteku
                    </Button>
                  )}
                  <button
                    type="button"
                    onClick={() => router.push("/pacijenti")}
                    className="text-xs text-muted-foreground hover:text-foreground underline-offset-2 hover:underline"
                  >
                    Pretraži kartoteku
                  </button>
                </div>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
