"use client"

import { useState } from "react"
import { useForm } from "react-hook-form"
import { standardSchemaResolver } from "@hookform/resolvers/standard-schema"
import { z } from "zod"
import { Plus, Pencil, Trash2, Lock, ShieldCheck, Loader2, X } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PageHeader } from "@/components/shared/page-header"
import { LoadingSpinner } from "@/components/shared/loading-spinner"
import { useRecordTypes, useCreateRecordType, useUpdateRecordType, useDeleteRecordType } from "@/lib/hooks/use-record-types"

const COLOR_SWATCHES = [
  { value: "bg-slate-100 text-slate-800", label: "Siva" },
  { value: "bg-orange-100 text-orange-800", label: "Narančasta" },
  { value: "bg-lime-100 text-lime-800", label: "Limunasta" },
  { value: "bg-sky-100 text-sky-800", label: "Plava" },
  { value: "bg-violet-100 text-violet-800", label: "Ljubičasta" },
  { value: "bg-fuchsia-100 text-fuchsia-800", label: "Fuksija" },
  { value: "bg-pink-100 text-pink-800", label: "Ružičasta" },
  { value: "bg-teal-100 text-teal-800", label: "Tirkizna" },
  { value: "bg-zinc-100 text-zinc-800", label: "Cink" },
  { value: "bg-stone-100 text-stone-800", label: "Kamen" },
  { value: "bg-amber-100 text-amber-800", label: "Jantarna" },
  { value: "bg-emerald-100 text-emerald-800", label: "Smaragdna" },
  { value: "bg-indigo-100 text-indigo-800", label: "Indigo" },
  { value: "bg-rose-100 text-rose-800", label: "Ruža" },
  { value: "bg-cyan-100 text-cyan-800", label: "Cijan" },
  { value: "bg-blue-100 text-blue-800", label: "Plava" },
  { value: "bg-red-100 text-red-800", label: "Crvena" },
  { value: "bg-green-100 text-green-800", label: "Zelena" },
  { value: "bg-purple-100 text-purple-800", label: "Ljubičasta" },
]

const formSchema = z.object({
  slug: z.string().regex(/^[a-z][a-z0-9_]{1,48}$/, "Slug: mala slova, brojevi i podvlake (2-50 znakova)"),
  label: z.string().min(2, "Naziv mora imati najmanje 2 znaka"),
})

type FormData = z.infer<typeof formSchema>

export default function TipoviZapisaPage() {
  const { data: recordTypes, isLoading } = useRecordTypes(false)
  const createMutation = useCreateRecordType()
  const updateMutation = useUpdateRecordType()
  const deleteMutation = useDeleteRecordType()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editLabel, setEditLabel] = useState("")
  const [editColor, setEditColor] = useState<string | null>(null)
  const [selectedColor, setSelectedColor] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormData>({
    resolver: standardSchemaResolver(formSchema),
  })

  const openCreate = () => {
    reset({ slug: "", label: "" })
    setSelectedColor(null)
    setDialogOpen(true)
  }

  const openEdit = (id: string, label: string, color: string | null) => {
    setEditingId(id)
    setEditLabel(label)
    setEditColor(color)
  }

  const closeEdit = () => {
    setEditingId(null)
    setEditLabel("")
    setEditColor(null)
  }

  const onCreateSubmit = (data: FormData) => {
    createMutation.mutate(
      { slug: data.slug, label: data.label, color: selectedColor },
      {
        onSuccess: () => {
          toast.success("Tip zapisa kreiran")
          setDialogOpen(false)
          reset()
          setSelectedColor(null)
        },
        onError: (err) => toast.error(err.message),
      }
    )
  }

  const handleUpdate = () => {
    if (!editingId || !editLabel.trim()) return
    updateMutation.mutate(
      { id: editingId, data: { label: editLabel.trim(), color: editColor } },
      {
        onSuccess: () => {
          toast.success("Tip zapisa ažuriran")
          closeEdit()
        },
        onError: (err) => toast.error(err.message),
      }
    )
  }

  const handleDelete = (id: string) => {
    if (!confirm("Sigurno želite obrisati ovaj tip zapisa?")) return
    deleteMutation.mutate(id, {
      onSuccess: () => toast.success("Tip zapisan obrisan"),
      onError: (err) => toast.error(err.message),
    })
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader title="Tip nalaza" />
        <LoadingSpinner text="Učitavanje..." />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Tip nalaza">
        <Button onClick={openCreate}>
          <Plus className="mr-2 h-4 w-4" />
          Dodaj tip
        </Button>
      </PageHeader>

      {/* Create dialog */}
      {dialogOpen && (
        <dialog open className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-[calc(100%-2rem)] sm:max-w-md max-h-[90vh] overflow-y-auto rounded-xl bg-popover p-4 text-sm text-popover-foreground ring-1 ring-foreground/10 shadow-lg backdrop:bg-black/10 backdrop:backdrop-blur-xs m-0">
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h2 className="font-heading text-base font-medium">Novi tip zapisa</h2>
              <button type="button" onClick={() => setDialogOpen(false)} className="rounded-md p-1 hover:bg-muted transition-colors">
                <X className="h-4 w-4" />
              </button>
            </div>
            <form onSubmit={handleSubmit(onCreateSubmit)} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="rt-slug">Slug (identifikator)</Label>
                <Input id="rt-slug" placeholder="npr. rtg_nalaz" {...register("slug")} />
                <p className="text-xs text-muted-foreground">Mala slova, brojevi i podvlake. Koristi se u sustavu.</p>
                {errors.slug && <p className="text-xs text-destructive">{errors.slug.message}</p>}
              </div>
              <div className="space-y-2">
                <Label htmlFor="rt-label">Naziv</Label>
                <Input id="rt-label" placeholder="npr. RTG nalaz" {...register("label")} />
                {errors.label && <p className="text-xs text-destructive">{errors.label.message}</p>}
              </div>
              <div className="space-y-2">
                <Label>Boja</Label>
                <div className="grid grid-cols-5 gap-2">
                  {COLOR_SWATCHES.map((swatch) => (
                    <button
                      key={swatch.value}
                      type="button"
                      onClick={() => setSelectedColor(swatch.value === selectedColor ? null : swatch.value)}
                      className={`rounded-md px-2 py-1.5 text-xs font-medium border transition-all cursor-pointer ${swatch.value} ${selectedColor === swatch.value ? "ring-2 ring-primary ring-offset-1" : "border-transparent"}`}
                    >
                      {swatch.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
                  Odustani
                </Button>
                <Button type="submit" disabled={createMutation.isPending}>
                  {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Kreiraj
                </Button>
              </div>
            </form>
          </div>
        </dialog>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Svi tipovi nalaza</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="pb-2 pr-4 font-medium text-muted-foreground">Naziv</th>
                  <th className="pb-2 pr-4 font-medium text-muted-foreground">Slug</th>
                  <th className="pb-2 pr-4 font-medium text-muted-foreground">Boja</th>
                  <th className="pb-2 pr-4 font-medium text-muted-foreground">CEZIH</th>
                  <th className="pb-2 pr-4 font-medium text-muted-foreground">Status</th>
                  <th className="pb-2 font-medium text-muted-foreground">Radnje</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {recordTypes?.map((rt) => (
                  <tr key={rt.id} className={!rt.is_active ? "opacity-50" : ""}>
                    <td className="py-3 pr-4">
                      <div className="flex items-center gap-2">
                        {rt.is_cezih_mandatory ? (
                          <Lock className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                        ) : rt.is_system ? (
                          <ShieldCheck className="h-3.5 w-3.5 text-blue-500 shrink-0" />
                        ) : null}
                        <span className="font-medium">
                          {editingId === rt.id ? (
                            <Input
                              value={editLabel}
                              onChange={(e) => setEditLabel(e.target.value)}
                              onKeyDown={(e) => e.key === "Enter" && handleUpdate()}
                              className="h-7 w-48"
                            />
                          ) : (
                            rt.label
                          )}
                        </span>
                      </div>
                    </td>
                    <td className="py-3 pr-4">
                      <code className="text-xs bg-muted px-1.5 py-0.5 rounded">{rt.slug}</code>
                    </td>
                    <td className="py-3 pr-4">
                      {editingId === rt.id ? (
                        <select
                          value={editColor ?? ""}
                          onChange={(e) => setEditColor(e.target.value || null)}
                          className="h-7 text-xs rounded border border-input bg-transparent px-1"
                        >
                          <option value="">Zadano</option>
                          {COLOR_SWATCHES.map((s) => (
                            <option key={s.value} value={s.value}>{s.label}</option>
                          ))}
                        </select>
                      ) : rt.color ? (
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${rt.color}`}>
                          Primjer
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="py-3 pr-4">
                      {rt.is_cezih_mandatory ? (
                        <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded">
                          Obavezan
                        </span>
                      ) : rt.is_cezih_eligible ? (
                        <span className="inline-flex items-center gap-1 text-xs font-medium text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded">
                          Moguće
                        </span>
                      ) : (
                        <span className="text-muted-foreground text-xs">—</span>
                      )}
                    </td>
                    <td className="py-3 pr-4">
                      <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${rt.is_active ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-500"}`}>
                        {rt.is_active ? "Aktivan" : "Neaktivan"}
                      </span>
                    </td>
                    <td className="py-3">
                      <div className="flex items-center gap-1">
                        {editingId === rt.id ? (
                          <>
                            <Button size="sm" variant="default" onClick={handleUpdate} disabled={updateMutation.isPending} className="h-7 px-2">
                              {updateMutation.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Spremi"}
                            </Button>
                            <Button size="sm" variant="ghost" onClick={closeEdit} className="h-7 px-2">Odustani</Button>
                          </>
                        ) : (
                          <>
                            {!rt.is_cezih_mandatory && (
                              <Button size="sm" variant="ghost" onClick={() => openEdit(rt.id, rt.label, rt.color)} className="h-7 px-2">
                                <Pencil className="h-3.5 w-3.5" />
                              </Button>
                            )}
                            {!rt.is_system && (
                              <Button size="sm" variant="ghost" onClick={() => handleDelete(rt.id)} className="h-7 px-2 text-destructive hover:text-destructive">
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            )}
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
