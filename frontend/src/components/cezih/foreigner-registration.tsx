"use client"

import { useState } from "react"
import { Globe, Loader2, CheckCircle, ExternalLink } from "lucide-react"
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
import { useRegisterForeigner } from "@/lib/hooks/use-cezih"

const EHIC_REGEX = /^[0-9A-Za-z]{20}$/
const PASSPORT_REGEX = /^[A-Za-z0-9]{5,15}$/
const COUNTRY_REGEX = /^[A-Za-z]{2,3}$/

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
