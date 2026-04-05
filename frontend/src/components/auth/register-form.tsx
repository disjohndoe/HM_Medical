"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { standardSchemaResolver } from "@hookform/resolvers/standard-schema";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const registerSchema = z
  .object({
    naziv_klinike: z.string().min(2, "Naziv klinike je obavezan"),
    vrsta: z.enum(["ordinacija", "poliklinika", "dom_zdravlja"]),
    ime: z.string().min(2, "Ime je obavezno"),
    prezime: z.string().min(2, "Prezime je obavezno"),
    email: z.email("Unesite ispravnu email adresu"),
    password: z.string()
      .min(8, "Lozinka mora imati najmanje 8 znakova")
      .regex(/[A-Z]/, "Lozinka mora sadržavati barem jedno veliko slovo")
      .regex(/[a-z]/, "Lozinka mora sadržavati barem jedno malo slovo")
      .regex(/\d/, "Lozinka mora sadržavati barem jedan broj")
      .regex(/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?`~]/, "Lozinka mora sadržavati barem jedan posebni znak"),
    confirmPassword: z.string().min(1, "Potvrda lozinke je obavezna"),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Lozinke se ne podudaraju",
    path: ["confirmPassword"],
  });

type RegisterForm = z.infer<typeof registerSchema>;

export function RegisterForm() {
  const { register: registerUser } = useAuth();
  const router = useRouter();
  const [error, setError] = useState("");

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<RegisterForm>({
    resolver: standardSchemaResolver(registerSchema),
    defaultValues: { vrsta: "ordinacija" },
  });

  const onSubmit = async (data: RegisterForm) => {
    try {
      setError("");
      const { confirmPassword, ...payload } = data;
      void confirmPassword;
      await registerUser(payload);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Greška pri registraciji");
    }
  };

  return (
    <Card className="w-full max-w-md">
      <CardHeader className="text-center">
        <CardTitle className="text-2xl">Registracija</CardTitle>
        <CardDescription>
          14 dana besplatnog trial perioda
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit(onSubmit)}>
        <CardContent className="space-y-4">
          {error && (
            <div className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}
          <div className="space-y-2">
            <Label htmlFor="naziv_klinike">Naziv klinike</Label>
            <Input id="naziv_klinike" placeholder="Ordinacija Smith" {...register("naziv_klinike")} />
            {errors.naziv_klinike && <p className="text-sm text-destructive">{errors.naziv_klinike.message}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="vrsta">Vrsta ustanove</Label>
            <Select defaultValue="ordinacija" onValueChange={(v) => setValue("vrsta", v as RegisterForm["vrsta"])}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ordinacija">Privatna ordinacija</SelectItem>
                <SelectItem value="poliklinika">Poliklinika</SelectItem>
                <SelectItem value="dom_zdravlja">Dom zdravlja</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="ime">Ime</Label>
              <Input id="ime" {...register("ime")} />
              {errors.ime && <p className="text-sm text-destructive">{errors.ime.message}</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="prezime">Prezime</Label>
              <Input id="prezime" {...register("prezime")} />
              {errors.prezime && <p className="text-sm text-destructive">{errors.prezime.message}</p>}
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" placeholder="ime@klinika.hr" {...register("email")} />
            {errors.email && <p className="text-sm text-destructive">{errors.email.message}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Lozinka</Label>
            <Input id="password" type="password" {...register("password")} />
            <p className="text-xs text-muted-foreground">
              Najmanje 8 znakova, veliko slovo, malo slovo, broj i posebni znak (+, *, $, ! ...)
            </p>
            {errors.password && <p className="text-sm text-destructive">{errors.password.message}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirmPassword">Potvrdi lozinku</Label>
            <Input id="confirmPassword" type="password" {...register("confirmPassword")} />
            {errors.confirmPassword && (
              <p className="text-sm text-destructive">{errors.confirmPassword.message}</p>
            )}
          </div>
        </CardContent>
        <CardFooter className="flex flex-col gap-3">
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? "Registracija..." : "Registrirajte se besplatno"}
          </Button>
          <p className="text-sm text-muted-foreground">
            Već imate račun?{" "}
            <Link href="/prijava" className="text-primary underline underline-offset-4 hover:text-primary/80">
              Prijavite se
            </Link>
          </p>
        </CardFooter>
      </form>
    </Card>
  );
}
