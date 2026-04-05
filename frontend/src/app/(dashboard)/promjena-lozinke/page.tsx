"use client"

import { useForm } from "react-hook-form"
import { standardSchemaResolver } from "@hookform/resolvers/standard-schema"
import { z } from "zod"
import { Save, Loader2 } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { PageHeader } from "@/components/shared/page-header"
import { api } from "@/lib/api-client"
import { useMutation } from "@tanstack/react-query"

const passwordSchema = z
  .object({
    old_password: z.string().min(1, "Stara lozinka je obavezna"),
    new_password: z.string()
      .min(8, "Nova lozinka mora imati najmanje 8 znakova")
      .regex(/[A-Z]/, "Lozinka mora sadržavati barem jedno veliko slovo")
      .regex(/[a-z]/, "Lozinka mora sadržavati barem jedno malo slovo")
      .regex(/\d/, "Lozinka mora sadržavati barem jedan broj")
      .regex(/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?`~]/, "Lozinka mora sadržavati barem jedan posebni znak"),
    confirm_password: z.string().min(1, "Potvrdite novu lozinku"),
  })
  .refine((data) => data.new_password === data.confirm_password, {
    message: "Lozinke se ne podudaraju",
    path: ["confirm_password"],
  })

type PasswordForm = z.infer<typeof passwordSchema>

export default function PromjenaLozinkePage() {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<PasswordForm>({
    resolver: standardSchemaResolver(passwordSchema),
  })

  const changePassword = useMutation({
    mutationFn: (data: { old_password: string; new_password: string }) =>
      api.post("/auth/change-password", data),
    onSuccess: () => {
      toast.success("Lozinka uspješno promijenjena")
      reset()
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "Greška pri promjeni lozinke")
    },
  })

  const onSubmit = (data: PasswordForm) => {
    changePassword.mutate({
      old_password: data.old_password,
      new_password: data.new_password,
    })
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Promjena lozinke" />

      <Card className="max-w-md">
        <CardHeader>
          <CardTitle className="text-lg">Nova lozinka</CardTitle>
          <CardDescription>
            Unesite staru lozinku i odaberite novu.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="old_password">Stara lozinka</Label>
              <Input id="old_password" type="password" {...register("old_password")} />
              {errors.old_password && (
                <p className="text-xs text-destructive">{errors.old_password.message}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="new_password">Nova lozinka</Label>
              <Input id="new_password" type="password" {...register("new_password")} />
              <p className="text-xs text-muted-foreground">
                Najmanje 8 znakova, veliko slovo, malo slovo, broj i posebni znak (+, *, $, ! ...)
              </p>
              {errors.new_password && (
                <p className="text-xs text-destructive">{errors.new_password.message}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="confirm_password">Potvrdite novu lozinku</Label>
              <Input id="confirm_password" type="password" {...register("confirm_password")} />
              {errors.confirm_password && (
                <p className="text-xs text-destructive">{errors.confirm_password.message}</p>
              )}
            </div>

            <Button type="submit" disabled={changePassword.isPending}>
              {changePassword.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              <Save className="mr-2 h-4 w-4" />
              Promijeni lozinku
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
