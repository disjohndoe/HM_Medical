"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { usePermissions } from "@/lib/hooks/use-permissions";
import { useCezihOpenVisitsCount, useCezihActiveCasesCount } from "@/lib/hooks/use-cezih";
import { NAV_ITEMS } from "@/lib/constants";

export function MobileNav({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { tenant } = useAuth();
  const perms = usePermissions();
  const { data: openVisitsCount } = useCezihOpenVisitsCount();
  const { data: activeCasesCount } = useCezihActiveCasesCount();

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="left" className="w-72 p-0">
        <SheetHeader className="px-4 py-4">
          <SheetTitle className="text-sm font-semibold truncate">
            {tenant?.naziv ?? "HM Digital"}
          </SheetTitle>
        </SheetHeader>

        <nav className="flex flex-col gap-1 px-2 pb-4">
          {NAV_ITEMS.filter((item) => !item.perm || perms[item.perm]).map((item) => {
            const hrefPath = item.href.split("?")[0];
            const itemTab = item.href.split("tab=")[1];
            const isActive =
              (pathname === hrefPath || pathname.startsWith(hrefPath + "/")) &&
              // Tab-scoped entries (the /cezih sub-pages) only light up when
              // their own tab is open, so the CEZIH items don't highlight together.
              (!itemTab || searchParams.get("tab") === itemTab);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => onOpenChange(false)}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                )}
              >
                <item.icon className="h-4 w-4 shrink-0" />
                <span className="flex-1">{item.label}</span>
                {item.href === "/cezih?tab=slucajevi" && (activeCasesCount ?? 0) > 0 && (
                  <span
                    title={`${activeCasesCount} aktivnih slučajeva (nije zatvoreno)`}
                    aria-label={`${activeCasesCount} aktivnih slučajeva`}
                    className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800"
                  >
                    {activeCasesCount}
                  </span>
                )}
                {item.href === "/cezih?tab=posjete" && (openVisitsCount ?? 0) > 0 && (
                  <span
                    title={`${openVisitsCount} otvorenih posjeta (nije zatvoreno)`}
                    aria-label={`${openVisitsCount} otvorenih posjeta`}
                    className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800"
                  >
                    {openVisitsCount}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>
      </SheetContent>
    </Sheet>
  );
}
