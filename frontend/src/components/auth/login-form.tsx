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

const loginSchema = z.object({
  email: z.email("Unesite ispravnu email adresu"),
  password: z.string().min(1, "Lozinka je obavezna"),
});

type LoginForm = z.infer<typeof loginSchema>;

export function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const [error, setError] = useState("");

  // Show reason for redirect (kicked session, expired token)
  const [info] = useState(() => {
    if (typeof window === "undefined") return "";
    const reason = localStorage.getItem("auth_redirect_reason");
    if (reason) {
      localStorage.removeItem("auth_redirect_reason");
      if (reason === "session_expired") {
        return "Vaša sesija je istekla. Prijavite se ponovo.";
      }
    }
    return "";
  });

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginForm>({
    resolver: standardSchemaResolver(loginSchema),
  });

  const onSubmit = async (data: LoginForm) => {
    try {
      setError("");
      await login(data);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Greška pri prijavi");
    }
  };

  return (
    <Card className="w-full max-w-md">
      <CardHeader className="text-center">
        <CardTitle className="text-2xl">Prijava</CardTitle>
        <CardDescription>Prijavite se u svoj račun</CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit(onSubmit)}>
        <CardContent className="space-y-4">
          {info && (
            <div className="rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-700 dark:bg-blue-950 dark:text-blue-300">
              {info}
            </div>
          )}
          {error && (
            <div className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" placeholder="ime@klinika.hr" {...register("email")} />
            {errors.email && <p className="text-sm text-destructive">{errors.email.message}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Lozinka</Label>
            <Input id="password" type="password" {...register("password")} />
            {errors.password && <p className="text-sm text-destructive">{errors.password.message}</p>}
          </div>
        </CardContent>
        <CardFooter className="flex flex-col gap-3">
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? "Prijava..." : "Prijava"}
          </Button>
          <p className="text-sm text-muted-foreground">
            Nemate račun?{" "}
            <Link href="/registracija" className="text-primary underline underline-offset-4 hover:text-primary/80">
              Registrirajte se
            </Link>
          </p>
        </CardFooter>
      </form>
    </Card>
  );
}
