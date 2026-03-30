"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { LogOut, Menu, KeyRound } from "lucide-react";
import { MobileNav } from "./mobile-nav";
import { useState } from "react";

const roleLabels: Record<string, string> = {
  admin: "Admin",
  doctor: "Liječnik",
  nurse: "Med. sestra",
  receptionist: "Recepcija",
};

export function Header() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);

  const initials = user
    ? `${user.ime.charAt(0)}${user.prezime.charAt(0)}`.toUpperCase()
    : "?";

  const handleLogout = async () => {
    await logout();
    router.replace("/prijava");
  };

  return (
    <>
      <header className="flex h-14 items-center gap-4 border-b bg-background px-4 lg:px-6">
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden"
          onClick={() => setMobileOpen(true)}
        >
          <Menu className="h-5 w-5" />
          <span className="sr-only">Izbornik</span>
        </Button>

        <div className="flex-1" />

        <div className="flex items-center gap-3">
          {user && (
            <>
              <Badge variant="outline" className="hidden sm:inline-flex">
                {roleLabels[user.role] ?? user.role}
              </Badge>
              <DropdownMenu>
                <DropdownMenuTrigger
                  className="flex items-center gap-2 rounded-lg px-2 py-1 hover:bg-accent transition-colors"
                >
                  <Avatar size="sm">
                    <AvatarFallback>{initials}</AvatarFallback>
                  </Avatar>
                  <span className="text-sm font-medium hidden sm:block">
                    {user.ime} {user.prezime}
                  </span>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => router.push("/promjena-lozinke")}>
                    <KeyRound className="mr-2 h-4 w-4" />
                    Promijeni lozinku
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => handleLogout()}>
                    <LogOut className="mr-2 h-4 w-4" />
                    Odjava
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </>
          )}
        </div>
      </header>

      <MobileNav open={mobileOpen} onOpenChange={setMobileOpen} />
    </>
  );
}
