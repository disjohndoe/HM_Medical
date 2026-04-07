"use client"

import { useEffect, useMemo } from "react"
import { useForm, Controller } from "react-hook-form"
import { standardSchemaResolver } from "@hookform/resolvers/standard-schema"
import { z } from "zod"
import { Save, Loader2, CreditCard, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { USER_ROLE_OPTIONS } from "@/lib/constants"
import { useAutoBindCard, useUnbindCard, useCardStatus } from "@/lib/hooks/use-users"
import type { User } from "@/lib/types"
import { toast } from "sonner"

const userSchema = z.object({
  email: z.string().email("Neispravan email"),
  password: z.string()
    .optional()
    .or(z.literal(""))
    .refine(
      (val) => !val || val.length >= 8,
      "Lozinka mora imati najmanje 8 znakova"
    )
    .refine(
      (val) => !val || /[A-Z]/.test(val),
      "Lozinka mora sadržavati barem jedno veliko slovo"
    )
    .refine(
      (val) => !val || /[a-z]/.test(val),
      "Lozinka mora sadržavati barem jedno malo slovo"
    )
    .refine(
      (val) => !val || /\d/.test(val),
      "Lozinka mora sadržavati barem jedan broj"
    )
    .refine(
      (val) => !val || /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?`~]/.test(val),
      "Lozinka mora sadržavati barem jedan posebni znak"
    ),
  ime: z.string().min(1, "Ime je obavezno"),
  prezime: z.string().min(1, "Prezime je obavezno"),
  titula: z.string().nullable().optional(),
  telefon: z.string().nullable().optional(),
  role: z.string().min(1, "Uloga je obavezna"),
  practitioner_id: z.string().nullable().optional(),
})

export type UserFormData = z.infer<typeof userSchema>

interface UserFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  user?: User | null
  onSubmit: (data: UserFormData) => void
  isPending: boolean
}

export function UserFormDialog({
  open,
  onOpenChange,
  user,
  onSubmit,
  isPending,
}: UserFormDialogProps) {
  const isEdit = !!user
  const autoBindCard = useAutoBindCard()
  const unbindCard = useUnbindCard()
  const { data: cardStatus } = useCardStatus()

  const handleAutoBind = () => {
    if (!user) return
    autoBindCard.mutate(user.id, {
      onSuccess: () => toast.success("Kartica povezana"),
      onError: (err) => toast.error(err.message),
    })
  }

  const handleUnbind = () => {
    if (!user) return
    unbindCard.mutate(user.id, {
      onSuccess: () => toast.success("Kartica odpojena"),
      onError: (err) => toast.error(err.message),
    })
  }

  const defaultFormValues: UserFormData = useMemo(() => ({
    email: user?.email ?? "",
    password: "",
    ime: user?.ime ?? "",
    prezime: user?.prezime ?? "",
    titula: user?.titula ?? null,
    telefon: user?.telefon ?? null,
    role: user?.role ?? "doctor",
    practitioner_id: user?.practitioner_id ?? null,
  }), [user])

  const {
    register,
    handleSubmit,
    reset,
    control,
    formState: { errors },
  } = useForm<UserFormData>({
    resolver: standardSchemaResolver(userSchema),
    defaultValues: defaultFormValues,
  })

  useEffect(() => {
    reset(defaultFormValues)
  }, [user, defaultFormValues, reset])

  const handleFormSubmit = (data: UserFormData) => {
    const payload = { ...data }
    if (isEdit && !payload.password) {
      delete payload.password
    }
    onSubmit(payload)
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) reset()
        onOpenChange(o)
      }}
    >
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Uredi korisnika" : "Novi korisnik"}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="ime">Ime</Label>
              <Input id="ime" {...register("ime")} />
              {errors.ime && (
                <p className="text-xs text-destructive">{errors.ime.message}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="prezime">Prezime</Label>
              <Input id="prezime" {...register("prezime")} />
              {errors.prezime && (
                <p className="text-xs text-destructive">
                  {errors.prezime.message}
                </p>
              )}
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="titula">Titula</Label>
            <Input id="titula" placeholder="dr. med., spec. ..." {...register("titula")} />
          </div>

          <div className="space-y-2">
            <Label htmlFor="practitioner_id">HZJZ broj</Label>
            <Input id="practitioner_id" placeholder="Broj zdravstvenog djelatnika" {...register("practitioner_id")} />
          </div>

          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" {...register("email")} />
            {errors.email && (
              <p className="text-xs text-destructive">{errors.email.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="password">
              {isEdit ? "Nova lozinka (prazno = nema promjene)" : "Lozinka"}
            </Label>
            <Input
              id="password"
              type="password"
              {...register("password")}
            />
            <p className="text-xs text-muted-foreground">
              Najmanje 8 znakova, veliko slovo, malo slovo, broj i posebni znak (+, *, $, ! ...)
            </p>
            {errors.password && (
              <p className="text-xs text-destructive">
                {errors.password.message}
              </p>
            )}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="telefon">Telefon</Label>
              <Input id="telefon" {...register("telefon")} />
            </div>
            <div className="space-y-2">
              <Label>Uloga</Label>
              <Controller
                name="role"
                control={control}
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger>
                      <SelectValue>
                        {USER_ROLE_OPTIONS.find((o) => o.value === (field.value ?? user?.role ?? "doctor"))?.label}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {USER_ROLE_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
              {errors.role && (
                <p className="text-xs text-destructive">{errors.role.message}</p>
              )}
            </div>
          </div>

          {isEdit && user && (
            <div className="space-y-2 rounded-lg border p-3">
              <Label className="flex items-center gap-1.5 text-sm font-medium">
                <CreditCard className="h-4 w-4" />
                AKD Kartica
              </Label>
              {user.card_holder_name ? (
                <div className="flex items-center justify-between">
                  <span className="text-sm">{user.card_holder_name}</span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={handleUnbind}
                    disabled={unbindCard.isPending}
                  >
                    {unbindCard.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <X className="h-4 w-4" />
                    )}
                    Odpoji
                  </Button>
                </div>
              ) : (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Nema povezane kartice</span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleAutoBind}
                    disabled={autoBindCard.isPending || !cardStatus?.card_inserted}
                    title={!cardStatus?.agent_connected ? "Agent nije spojen" : !cardStatus?.card_inserted ? "Kartica nije umetnuta" : "Poveži trenutnu karticu"}
                  >
                    {autoBindCard.isPending ? (
                      <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                    ) : (
                      <CreditCard className="mr-1 h-4 w-4" />
                    )}
                    Poveži karticu
                  </Button>
                </div>
              )}
            </div>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Odustani
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              <Save className="mr-2 h-4 w-4" />
              {isEdit ? "Spremi" : "Kreiraj"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
