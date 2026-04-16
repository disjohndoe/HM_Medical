"use client"

import { useState } from "react"
import { Search, Loader2, Plus } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  useOidGenerate,
  useOrganizationSearch,
  usePractitionerSearch,
  useValueSetExpand,
  useCodeSystemQuery,
} from "@/lib/hooks/use-cezih"

export function RegistryTools() {
  return (
    <div className="space-y-6">
      <OidGenerateCard />
      <CodeSystemQueryCard />
      <OrganizationSearchCard />
      <PractitionerSearchCard />
      <ValueSetExpandCard />
    </div>
  )
}

function OidGenerateCard() {
  const mutation = useOidGenerate()

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <CardTitle className="text-base">OID generiranje (TC6)</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          {mutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
          Generiraj OID
        </Button>
        {mutation.data && (
          <div className="rounded-lg border p-3 text-sm space-y-1">
            <div><span className="text-muted-foreground">Generirani OID:</span> <span className="font-mono select-all">{mutation.data.generated_oid}</span></div>
            {mutation.data.oids.length > 1 && (
              <div><span className="text-muted-foreground">Svi OID-ovi:</span> {mutation.data.oids.join(", ")}</div>
            )}
          </div>
        )}
        {mutation.error && (
          <p className="text-sm text-destructive">{mutation.error.message}</p>
        )}
      </CardContent>
    </Card>
  )
}

const CODE_SYSTEMS = [
  { value: "nacin-prijema", label: "Način prijema (nacin-prijema)" },
  { value: "vrsta-posjete", label: "Vrsta posjete (vrsta-posjete)" },
  { value: "hr-tip-posjete", label: "Tip posjete (hr-tip-posjete)" },
  { value: "djelatnosti-zz", label: "Djelatnosti (djelatnosti-zz)" },
  { value: "icd10-hr", label: "ICD-10 HR (icd10-hr)" },
]

function CodeSystemQueryCard() {
  const [system, setSystem] = useState("nacin-prijema")
  const [query, setQuery] = useState("")
  const { data: results, isLoading } = useCodeSystemQuery(system, query, true)

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <CardTitle className="text-base">Pretraga šifrarnika — SVCM ITI-96 (TC7)</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <Label className="text-xs">Šifrarnik</Label>
            <select
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs"
              value={system}
              onChange={(e) => setSystem(e.target.value)}
            >
              {CODE_SYSTEMS.map((cs) => (
                <option key={cs.value} value={cs.value}>{cs.label}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Pretraga (opcionalno)</Label>
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Kod ili naziv"
              className="text-xs"
            />
          </div>
        </div>
        {isLoading && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Pretraga...</div>}
        {results && results.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">Rezultata: {results.length}</p>
            {results.map((c) => (
              <div key={c.code} className="flex items-center gap-2 rounded-md bg-muted px-3 py-1.5 text-sm">
                <Badge variant="outline" className="font-mono text-xs">{c.code}</Badge>
                <span>{c.display}</span>
              </div>
            ))}
          </div>
        )}
        {results && results.length === 0 && (
          <p className="text-sm text-muted-foreground">Nema rezultata za odabrani šifrarnik</p>
        )}
      </CardContent>
    </Card>
  )
}

function OrganizationSearchCard() {
  const [query, setQuery] = useState("")
  const { data: results, isLoading } = useOrganizationSearch(query)

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <CardTitle className="text-base">Pretraga organizacija — mCSD ITI-90 (TC9)</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <Input
          placeholder="Naziv organizacije ili HZZO šifra (min. 2 znaka)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {isLoading && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Pretraga...</div>}
        {results && results.length > 0 && (
          <div className="space-y-1">
            {results.map((org) => (
              <div key={org.id} className="flex items-center justify-between rounded-md bg-muted px-3 py-2 text-sm">
                <div>
                  <span className="font-medium">{org.name}</span>
                  <span className="ml-2 text-xs text-muted-foreground">HZZO: {org.hzzo_code}</span>
                </div>
                <Badge variant={org.active ? "default" : "secondary"}>{org.active ? "Aktivna" : "Neaktivna"}</Badge>
              </div>
            ))}
          </div>
        )}
        {results && results.length === 0 && query.length >= 2 && (
          <p className="text-sm text-muted-foreground">Nema rezultata</p>
        )}
      </CardContent>
    </Card>
  )
}

function PractitionerSearchCard() {
  const [query, setQuery] = useState("")
  const { data: results, isLoading } = usePractitionerSearch(query)

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <CardTitle className="text-base">Pretraga djelatnika — mCSD ITI-90 (TC9)</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <Input
          placeholder="Ime, prezime ili HZJZ broj (min. 2 znaka)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {isLoading && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Pretraga...</div>}
        {results && results.length > 0 && (
          <div className="space-y-1">
            {results.map((p) => (
              <div key={p.id} className="flex items-center justify-between rounded-md bg-muted px-3 py-2 text-sm">
                <div>
                  <span className="font-medium">{p.given} {p.family}</span>
                  <span className="ml-2 text-xs text-muted-foreground">HZJZ: {p.hzjz_id}</span>
                </div>
                <Badge variant={p.active ? "default" : "secondary"}>{p.active ? "Aktivan" : "Neaktivan"}</Badge>
              </div>
            ))}
          </div>
        )}
        {results && results.length === 0 && query.length >= 2 && (
          <p className="text-sm text-muted-foreground">Nema rezultata</p>
        )}
      </CardContent>
    </Card>
  )
}

function ValueSetExpandCard() {
  const [url, setUrl] = useState("http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema")
  const [filter, setFilter] = useState("")
  const { data, isLoading, isFetching, refetch } = useValueSetExpand(url, filter)

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <CardTitle className="text-base">ValueSet — SVCM ITI-95 (TC8)</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <Label className="text-xs">ValueSet URL</Label>
            <Input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="URL skupa pojmova"
              className="text-xs"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Filter (opcionalno)</Label>
            <Input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filtriraj pojmove"
              className="text-xs"
            />
          </div>
        </div>
        <Button onClick={() => refetch()} disabled={!url || isFetching}>
          {isFetching ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Search className="mr-2 h-4 w-4" />}
          Proširi
        </Button>
        {isLoading && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Učitavanje...</div>}
        {data && (
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">Ukupno: {data.total} pojmova</p>
            {data.concepts.map((c) => (
              <div key={c.code} className="flex items-center gap-2 rounded-md bg-muted px-3 py-1.5 text-sm">
                <Badge variant="outline" className="font-mono text-xs">{c.code}</Badge>
                <span>{c.display}</span>
              </div>
            ))}
            {data.total === 0 && (
              <p className="text-sm text-muted-foreground">Prazan skup (testna okolina)</p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
