"use client"

import { useState } from "react"
import { Search, Loader2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  useOidLookup,
  useOrganizationSearch,
  usePractitionerSearch,
  useValueSetExpand,
} from "@/lib/hooks/use-cezih"

export function RegistryTools() {
  return (
    <div className="space-y-6">
      <OidLookupCard />
      <OrganizationSearchCard />
      <PractitionerSearchCard />
      <ValueSetExpandCard />
    </div>
  )
}

function OidLookupCard() {
  const [oid, setOid] = useState("")
  const mutation = useOidLookup()

  const handleSearch = () => {
    if (!oid.trim()) return
    mutation.mutate(oid.trim())
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <CardTitle className="text-base">OID registar (TC6)</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <Input
            placeholder="Unesite OID (npr. 2.16.840.1.113883.2.7...)"
            value={oid}
            onChange={(e) => setOid(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            className="flex-1"
          />
          <Button onClick={handleSearch} disabled={mutation.isPending || !oid.trim()}>
            {mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          </Button>
        </div>
        {mutation.data && (
          <div className="rounded-lg border p-3 text-sm space-y-1">
            <div><span className="text-muted-foreground">OID:</span> <span className="font-mono">{mutation.data.oid}</span></div>
            <div><span className="text-muted-foreground">Naziv:</span> {mutation.data.name}</div>
            <div><span className="text-muted-foreground">Organizacija:</span> {mutation.data.responsible_org}</div>
            <div><span className="text-muted-foreground">Status:</span> <Badge variant="secondary">{mutation.data.status}</Badge></div>
          </div>
        )}
        {mutation.error && (
          <p className="text-sm text-destructive">{mutation.error.message}</p>
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
  const [url, setUrl] = useState("http://terminology.hl7.org/CodeSystem/condition-ver-status")
  const [filter, setFilter] = useState("")
  const { data, isLoading } = useValueSetExpand(url, filter)

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
          </div>
        )}
      </CardContent>
    </Card>
  )
}
