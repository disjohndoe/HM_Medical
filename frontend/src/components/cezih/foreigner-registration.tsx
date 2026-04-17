"use client"

import { useEffect, useState } from "react"
import { Globe, Loader2, CheckCircle, ExternalLink, Search, UserPlus } from "lucide-react"
import { toast } from "sonner"
import Link from "next/link"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  useForeignerSearch,
  useImportPatientByIdentifier,
  useRegisterForeigner,
  type AdhocIdentifierType,
} from "@/lib/hooks/use-cezih"

const EHIC_REGEX = /^[0-9A-Za-z]{20}$/
const PASSPORT_REGEX = /^[A-Za-z0-9]{5,15}$/
const COUNTRY_REGEX = /^[A-Za-z]{2,3}$/

const SPOL_LABELS: Record<string, string> = { M: "Muški", Ž: "Ženski", Ostalo: "Ostalo", Nepoznato: "Nepoznato" }

export function ForeignerSearch() {
  const [system, setSystem] = useState("putovnica")
  const [value, setValue] = useState("")
  const [submitted, setSubmitted] = useState("")
  const [submittedSystem, setSubmittedSystem] = useState("")
  const [importedId, setImportedId] = useState<string | null>(null)

  const search = useForeignerSearch(submittedSystem, submitted)
  const importPatient = useImportPatientByIdentifier()

  useEffect(() => {
    setImportedId(null)
    importPatient.reset()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [submitted, submittedSystem])

  const handleSearch = () => {
    if (value.length < 5) {
      toast.error("Unesite valjani identifikator (min. 5 znakova)")
      return
    }
    setSubmittedSystem(system)
    setSubmitted(value)
  }

  const handleImport = () => {
    if (!submitted || !submittedSystem) return
    importPatient.mutate(
      {
        identifier_type: submittedSystem as AdhocIdentifierType,
        identifier_value: submitted,
      },
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

  const systemLabel = system === "putovnica" ? "Broj putovnice" : "EHIC broj"
  const existingLocalId = importedId || search.data?.local_patient_id || null

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-lg flex items-center gap-2">
          <Search className="h-5 w-5" />
          Pretraga stranca u CEZIH
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-3">
          <div className="w-48">
            <Label>Tip identifikatora</Label>
            <Select value={system} onValueChange={(v) => { if (v) { setSystem(v); setSubmitted(""); setValue("") } }}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="putovnica">Putovnica</SelectItem>
                <SelectItem value="ehic">EHIC kartica</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex-1">
            <Label>{systemLabel}</Label>
            <div className="flex gap-2">
              <Input
                value={value}
                onChange={(e) => setValue(e.target.value.toUpperCase())}
                placeholder={system === "putovnica" ? "AB1234567" : "20 znakova, npr. HR123..."}
                maxLength={system === "ehic" ? 20 : 15}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              />
              <Button onClick={handleSearch} disabled={search.isFetching || value.length < 5}>
                {search.isFetching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              </Button>
            </div>
          </div>
        </div>

        {search.isError && (
          <div className="flex items-center gap-2">
            <p className="text-sm text-red-600 flex-1">{(search.error as Error)?.message ?? "Pacijent nije pronađen"}</p>
            <Button variant="outline" size="sm" onClick={() => search.refetch()}>Pokušaj ponovo</Button>
          </div>
        )}

        {search.data && (
          <div className="p-3 rounded-lg bg-blue-50 border border-blue-200 space-y-1">
            <div className="flex items-center gap-2">
              <CheckCircle className="h-4 w-4 text-blue-600 shrink-0" />
              <span className="font-medium text-sm">Pronađen u CEZIH</span>
              {search.data.active === false && (
                <span className="text-xs text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded">Neaktivan</span>
              )}
              {search.data.datum_smrti && (
                <span className="text-xs text-red-700 bg-red-100 px-1.5 py-0.5 rounded">Preminuo</span>
              )}
            </div>
            <div className="text-sm grid grid-cols-2 gap-x-4 gap-y-1 mt-2">
              <span className="text-muted-foreground">Ime i prezime</span>
              <span className="font-medium">{search.data.prezime} {search.data.ime}</span>
              <span className="text-muted-foreground">Datum rođenja</span>
              <span>{search.data.datum_rodjenja || "—"}</span>
              <span className="text-muted-foreground">Spol</span>
              <span>{SPOL_LABELS[search.data.spol] ?? (search.data.spol || "—")}</span>
              {search.data.datum_smrti && (
                <>
                  <span className="text-muted-foreground">Datum smrti</span>
                  <span>{search.data.datum_smrti}</span>
                </>
              )}
              {search.data.zadnji_kontakt && (
                <>
                  <span className="text-muted-foreground">Zadnji kontakt</span>
                  <span>{search.data.zadnji_kontakt}</span>
                </>
              )}
              {search.data.adresa && (search.data.adresa.ulica || search.data.adresa.grad || search.data.adresa.drzava) && (
                <>
                  <span className="text-muted-foreground">Adresa</span>
                  <span>
                    {[
                      search.data.adresa.ulica,
                      [search.data.adresa.postanski_broj, search.data.adresa.grad].filter(Boolean).join(" "),
                      search.data.adresa.drzava,
                    ].filter(Boolean).join(", ")}
                  </span>
                </>
              )}
              {(search.data.telefon || search.data.email) && (
                <>
                  <span className="text-muted-foreground">Kontakt</span>
                  <span>{[search.data.telefon, search.data.email].filter(Boolean).join(" · ")}</span>
                </>
              )}
              {search.data.identifikatori && search.data.identifikatori.length > 0 ? (
                search.data.identifikatori.map((id) => (
                  <>
                    <span key={`lbl-${id.system}`} className="text-muted-foreground">{id.label}</span>
                    <span key={`val-${id.system}`} className="font-mono text-xs break-all">{id.value}</span>
                  </>
                ))
              ) : (
                <>
                  <span className="text-muted-foreground">CEZIH ID</span>
                  <span className="font-mono text-xs">{search.data.cezih_id}</span>
                </>
              )}
            </div>

            <div className="pt-2 flex items-center gap-2">
              {existingLocalId ? (
                <Button asChild size="sm" variant="outline">
                  <Link href={`/pacijenti/${existingLocalId}`}>
                    <ExternalLink className="mr-2 h-4 w-4" />
                    Otvori karton
                  </Link>
                </Button>
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
              {search.data.local_patient_id && !importedId && (
                <span className="text-xs text-muted-foreground">
                  Već u vašoj kartoteci
                </span>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function validate(form: {
  ime: string
  prezime: string
  datum_rodjenja: string
  broj_putovnice: string
  ehic_broj: string
  drzavljanstvo: string
}): string | null {
  if (!form.ime.trim()) return "Ime je obavezno"
  if (!form.prezime.trim()) return "Prezime je obavezno"
  if (!form.datum_rodjenja) return "Datum rođenja je obavezan"
  if (!form.broj_putovnice && !form.ehic_broj)
    return "Potreban je broj putovnice ili EHIC broj"
  if (form.broj_putovnice && !PASSPORT_REGEX.test(form.broj_putovnice))
    return "Broj putovnice: 5-15 alfanumeričkih znakova"
  if (form.ehic_broj && !EHIC_REGEX.test(form.ehic_broj))
    return "EHIC broj mora imati točno 20 alfanumeričkih znakova (0-9, A-Z)"
  if (form.drzavljanstvo && !COUNTRY_REGEX.test(form.drzavljanstvo))
    return "Državljanstvo: 2 ili 3 slova (npr. DE ili DEU)"
  return null
}

export function ForeignerRegistration() {
  const [form, setForm] = useState({
    ime: "",
    prezime: "",
    datum_rodjenja: "",
    spol: "unknown",
    drzavljanstvo: "",
    broj_putovnice: "",
    ehic_broj: "",
  })

  const register = useRegisterForeigner()

  const handleSubmit = () => {
    const err = validate(form)
    if (err) {
      toast.error(err)
      return
    }
    register.mutate(form, {
      onSuccess: (data) => {
        toast.success(`Stranac registriran u CEZIH (ID: ${data.patient_id})`)
      },
      onError: (e) => toast.error(e.message),
    })
  }

  const update = (field: string, value: string) =>
    setForm((prev) => ({ ...prev, [field]: value }))

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-lg flex items-center gap-2">
          <Globe className="h-5 w-5" />
          Registracija stranaca (PMIR)
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label>Ime *</Label>
            <Input
              value={form.ime}
              onChange={(e) => update("ime", e.target.value)}
              placeholder="John"
            />
          </div>
          <div>
            <Label>Prezime *</Label>
            <Input
              value={form.prezime}
              onChange={(e) => update("prezime", e.target.value)}
              placeholder="Smith"
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label>Datum rođenja *</Label>
            <Input
              type="date"
              value={form.datum_rodjenja}
              onChange={(e) => update("datum_rodjenja", e.target.value)}
            />
          </div>
          <div>
            <Label>Spol</Label>
            <Select value={form.spol} onValueChange={(v) => v && update("spol", v)}>
              <SelectTrigger>
                <SelectValue>
                  {{ male: "Muški", female: "Ženski", unknown: "Nepoznato" }[form.spol]}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="male">Muški</SelectItem>
                <SelectItem value="female">Ženski</SelectItem>
                <SelectItem value="unknown">Nepoznato</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label>Državljanstvo</Label>
            <Input
              value={form.drzavljanstvo}
              onChange={(e) => update("drzavljanstvo", e.target.value.toUpperCase())}
              placeholder="DE, AT, GB..."
              maxLength={3}
            />
            <p className="text-xs text-muted-foreground mt-1">ISO kod (2 ili 3 slova)</p>
          </div>
          <div>
            <Label>Broj putovnice *</Label>
            <Input
              value={form.broj_putovnice}
              onChange={(e) => update("broj_putovnice", e.target.value.toUpperCase())}
              placeholder="AB1234567"
              maxLength={15}
            />
          </div>
        </div>
        <div>
          <Label>EHIC broj (europska kartica, opcionalno)</Label>
          <Input
            value={form.ehic_broj}
            onChange={(e) => update("ehic_broj", e.target.value.toUpperCase())}
            placeholder="20 znakova, npr. HR12345678901234567X"
            maxLength={20}
          />
          <p className="text-xs text-muted-foreground mt-1">Točno 20 alfanumeričkih znakova (0-9, A-Z)</p>
        </div>
        <Button
          className="w-full"
          onClick={handleSubmit}
          disabled={register.isPending || !form.ime || !form.prezime || !form.datum_rodjenja}
        >
          {register.isPending ? (
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <Globe className="h-4 w-4 mr-2" />
          )}
          Registriraj stranca u CEZIH
        </Button>

        {register.data && (
          <div className="flex items-center gap-2 p-3 rounded-lg bg-green-50 border border-green-200">
            <CheckCircle className="h-5 w-5 text-green-600 shrink-0" />
            <div className="text-sm flex-1">
              <span className="font-medium">Registrirano!</span>{" "}
              {register.data.mbo && (
                <span>ID: <span className="font-mono">{register.data.mbo}</span></span>
              )}
              {register.data.local_patient_id && (
                <Link
                  href={`/pacijenti/${register.data.local_patient_id}`}
                  className="ml-2 inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 underline"
                >
                  Pogledaj kartoteku <ExternalLink className="h-3 w-3" />
                </Link>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
