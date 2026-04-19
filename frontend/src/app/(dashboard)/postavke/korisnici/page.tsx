"use client"

import { useState } from "react"
import { Plus, PencilIcon, Trash2, Loader2, CreditCard, Smartphone } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
import { TablePagination } from "@/components/shared/table-pagination"
import { UserFormDialog, type UserFormData } from "@/components/users/user-form-dialog"
import {
  useUsers,
  useCreateUser,
  useUpdateUser,
  useDeactivateUser,
} from "@/lib/hooks/use-users"
import { USER_ROLE } from "@/lib/constants"
import { usePlanUsage } from "@/lib/hooks/use-settings"
import { formatDateTimeHR } from "@/lib/utils"
import type { User, UserCreate } from "@/lib/types"

const PAGE_SIZE = 20

export default function KorisniciPage() {
  const [page, setPage] = useState(0)
  const { data: usersData, isLoading } = useUsers(page * PAGE_SIZE, PAGE_SIZE)
  const createUser = useCreateUser()
  const updateUser = useUpdateUser()
  const deactivateUser = useDeactivateUser()
  const { data: usage } = usePlanUsage()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<User | null>(null)

  const users = usersData?.items ?? []

  const { sorted: sortedUsers, sortKey: uSortKey, sortDir: uSortDir, toggleSort: toggleUSort } = useTableSort(users, {
    defaultKey: "last_login_at",
    defaultDir: "desc",
    keyAccessors: {
      ime_prezime: (u) => `${u.prezime ?? ""} ${u.ime ?? ""}`.trim(),
      uloga: (u) => u.role,
      status: (u) => (u.is_active ? 0 : 1),
      potpisivanje: (u) => u.cezih_signing_method,
    },
  })

  const handleCreate = (data: UserFormData) => {
    if (!data.password) return
    const createData: UserCreate = {
      email: data.email,
      password: data.password,
      ime: data.ime,
      prezime: data.prezime,
      role: data.role,
      titula: data.titula ?? undefined,
      telefon: data.telefon ?? undefined,
      practitioner_id: data.practitioner_id ?? undefined,
      mbo_lijecnika: data.mbo_lijecnika ?? undefined,
      cezih_signing_method: data.cezih_signing_method,
    }
    createUser.mutate(createData, {
      onSuccess: () => {
        toast.success("Korisnik kreiran")
        setDialogOpen(false)
      },
    })
  }

  const handleUpdate = (data: UserFormData) => {
    if (!editingUser) return
    updateUser.mutate(
      { id: editingUser.id, data },
      {
        onSuccess: () => {
          toast.success("Korisnik ažuriran")
          setDialogOpen(false)
          setEditingUser(null)
        },
      }
    )
  }

  const handleDeactivate = (user: User) => {
    if (!confirm(`Deaktivirati korisnika ${user.ime} ${user.prezime}?`)) return
    deactivateUser.mutate(user.id, {
      onSuccess: () => toast.success("Korisnik deaktiviran"),
    })
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader title="Korisnici" />
        <LoadingSpinner text="Učitavanje..." />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Korisnici">
        <div className="flex items-center gap-3">
          {usage && (
            <span className="text-sm text-muted-foreground">
              {usage.users.current} / {usage.users.max} korisnika
            </span>
          )}
          {!usage || usage.users.current < usage.users.max ? (
            <Button
              onClick={() => {
                setEditingUser(null)
                setDialogOpen(true)
              }}
            >
              <Plus className="mr-2 h-4 w-4" />
              Novi korisnik
            </Button>
          ) : (
            <p className="text-sm text-destructive font-medium">
              Dosegnut limit
            </p>
          )}
        </div>
      </PageHeader>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Popis korisnika</CardTitle>
        </CardHeader>
        <CardContent>
          {users.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8">
              <p className="text-sm text-muted-foreground">
                Nema korisnika
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <SortableTableHead columnKey="ime_prezime" label="Ime i prezime" currentKey={uSortKey} currentDir={uSortDir} onSort={toggleUSort} />
                  <SortableTableHead columnKey="email" label="Email" currentKey={uSortKey} currentDir={uSortDir} onSort={toggleUSort} className="hidden sm:table-cell" />
                  <SortableTableHead columnKey="uloga" label="Uloga" currentKey={uSortKey} currentDir={uSortDir} onSort={toggleUSort} />
                  <SortableTableHead columnKey="status" label="Status" currentKey={uSortKey} currentDir={uSortDir} onSort={toggleUSort} className="hidden md:table-cell" />
                  <SortableTableHead columnKey="potpisivanje" label="Kartica / Mobitel" currentKey={uSortKey} currentDir={uSortDir} onSort={toggleUSort} className="hidden md:table-cell" />
                  <SortableTableHead columnKey="last_login_at" label="Zadnja prijava" currentKey={uSortKey} currentDir={uSortDir} onSort={toggleUSort} className="hidden lg:table-cell" />
                  <TableHead className="text-right">Akcije</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedUsers.map((user) => (
                  <TableRow key={user.id}>
                    <TableCell className="font-medium">
                      {user.titula ? `${user.titula} ` : ""}
                      {user.ime} {user.prezime}
                    </TableCell>
                    <TableCell className="hidden sm:table-cell">{user.email}</TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {USER_ROLE[user.role] ?? user.role}
                      </Badge>
                    </TableCell>
                    <TableCell className="hidden md:table-cell">
                      <Badge variant={user.is_active ? "default" : "secondary"}>
                        {user.is_active ? "Aktivan" : "Neaktivan"}
                      </Badge>
                    </TableCell>
                    <TableCell className="hidden md:table-cell">
                      {user.cezih_signing_method === "smartcard" ? (
                        <Badge variant="outline" className="gap-1">
                          <CreditCard className="h-3 w-3" />
                          {user.card_holder_name || "Kartica"}
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="gap-1">
                          <Smartphone className="h-3 w-3" />
                          Mobitel
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="hidden lg:table-cell text-sm text-muted-foreground">
                      {formatDateTimeHR(user.last_login_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setEditingUser(user)
                            setDialogOpen(true)
                          }}
                        >
                          <PencilIcon className="h-4 w-4" />
                        </Button>
                        {user.is_active && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeactivate(user)}
                            disabled={deactivateUser.isPending}
                          >
                            {deactivateUser.isPending ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <Trash2 className="h-4 w-4 text-destructive" />
                            )}
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {usersData && usersData.total > 0 && (
        <TablePagination
          page={page}
          pageSize={PAGE_SIZE}
          total={usersData.total}
          onPageChange={setPage}
        />
      )}

      <UserFormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        user={editingUser}
        onSubmit={editingUser ? handleUpdate : handleCreate}
        isPending={createUser.isPending || updateUser.isPending}
      />
    </div>
  )
}
