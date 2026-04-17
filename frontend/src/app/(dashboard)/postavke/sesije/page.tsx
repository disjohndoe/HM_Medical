"use client"

import { Loader2, LogOut, Trash2 } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { SortableTableHead } from "@/components/ui/sortable-table-head"
import { useTableSort } from "@/lib/hooks/use-table-sort"
import { PageHeader } from "@/components/shared/page-header"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import {
  useSessions,
  useRevokeSession,
  useRevokeOtherSessions,
  useCleanupTokens,
} from "@/lib/hooks/use-sessions"
import { usePlanUsage } from "@/lib/hooks/use-settings"
import { useAuth } from "@/lib/auth"
import { formatDateTimeHR } from "@/lib/utils"

export default function SesijePage() {
  const { user } = useAuth()
  const { data: sessions, isLoading } = useSessions()
  const { data: usage } = usePlanUsage()
  const revokeSession = useRevokeSession()
  const revokeOthers = useRevokeOtherSessions()
  const cleanup = useCleanupTokens()

  const { sorted: sortedSessions, sortKey: sSortKey, sortDir: sSortDir, toggleSort: toggleSSort } = useTableSort(sessions, {
    defaultKey: "created_at",
    defaultDir: "desc",
    keyAccessors: {
      korisnik: (s) => `${s.user_prezime ?? ""} ${s.user_ime ?? ""}`.trim(),
      email: (s) => s.user_email,
    },
  })

  const handleRevoke = (sessionId: string) => {
    if (!confirm("Ukinuti ovu sesiju? Korisnik će biti odjavljen.")) return
    revokeSession.mutate(sessionId, {
      onSuccess: () => toast.success("Sesija ukinuta"),
      onError: (err) => toast.error(err.message),
    })
  }

  const handleRevokeOthers = () => {
    if (!confirm("Ukinuti sve ostale sesije? Svi drugi korisnici će biti odjavljeni.")) return
    revokeOthers.mutate(undefined, {
      onSuccess: (data) =>
        toast.success(`Ukinuto ${data.revoked_count} sesija`),
      onError: (err) => toast.error(err.message),
    })
  }

  const handleCleanup = () => {
    cleanup.mutate(undefined, {
      onSuccess: (data) =>
        toast.success(`Očišćeno ${data.cleaned_count} isteklih tokena`),
      onError: (err) => toast.error(err.message),
    })
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader title="Aktivne sesije" />
        <LoadingSpinner text="Učitavanje..." />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Aktivne sesije">
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleCleanup}
            disabled={cleanup.isPending}
          >
            {cleanup.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="mr-2 h-4 w-4" />
            )}
            Očisti istekle
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={handleRevokeOthers}
            disabled={revokeOthers.isPending}
          >
            {revokeOthers.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <LogOut className="mr-2 h-4 w-4" />
            )}
            Odjavi sve ostale
          </Button>
        </div>
      </PageHeader>

      {usage && (
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Aktivne sesije</span>
              <span className="font-medium">
                {sessions?.length ?? usage.sessions.current} / {usage.sessions.max}
              </span>
            </div>
            <div className="mt-2 h-2 rounded-full bg-muted overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  (sessions?.length ?? usage.sessions.current) >= usage.sessions.max
                    ? "bg-destructive"
                    : "bg-primary"
                }`}
                style={{
                  width: `${Math.min(
                    100,
                    ((sessions?.length ?? usage.sessions.current) / usage.sessions.max) * 100
                  )}%`,
                }}
              />
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Popis sesija</CardTitle>
          <CardDescription>
            Sve aktivne sesije vaše klinike. Ukinite sesiju da odjavite korisnika s tog uređaja.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!sessions || sessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8">
              <p className="text-sm text-muted-foreground">
                Nema aktivnih sesija
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <SortableTableHead columnKey="korisnik" label="Korisnik" currentKey={sSortKey} currentDir={sSortDir} onSort={toggleSSort} />
                  <SortableTableHead columnKey="email" label="Email" currentKey={sSortKey} currentDir={sSortDir} onSort={toggleSSort} className="hidden sm:table-cell" />
                  <SortableTableHead columnKey="created_at" label="Prijavljen" currentKey={sSortKey} currentDir={sSortDir} onSort={toggleSSort} className="hidden md:table-cell" />
                  <SortableTableHead columnKey="expires_at" label="Ističe" currentKey={sSortKey} currentDir={sSortDir} onSort={toggleSSort} className="hidden lg:table-cell" />
                  <TableHead className="text-right">Akcije</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedSessions.map((session) => {
                  const isCurrentUser = session.user_id === user?.id
                  return (
                    <TableRow key={session.id}>
                      <TableCell className="font-medium">
                        {session.user_ime} {session.user_prezime}
                        {isCurrentUser && (
                          <Badge variant="secondary" className="ml-2 text-xs">
                            Vi
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="hidden sm:table-cell">
                        {session.user_email}
                      </TableCell>
                      <TableCell className="hidden md:table-cell text-sm text-muted-foreground">
                        {formatDateTimeHR(session.created_at)}
                      </TableCell>
                      <TableCell className="hidden lg:table-cell text-sm text-muted-foreground">
                        {formatDateTimeHR(session.expires_at)}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRevoke(session.id)}
                          disabled={revokeSession.isPending}
                        >
                          {revokeSession.isPending ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <LogOut className="h-4 w-4 text-destructive" />
                          )}
                        </Button>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
