"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { PLAN_TIER, CEZIH_STATUS, CEZIH_STATUS_COLORS, NAV_ITEMS } from "@/lib/constants";
import { useCezihStatus } from "@/lib/hooks/use-cezih";
import { usePermissions } from "@/lib/hooks/use-permissions";

export function Sidebar() {
  const pathname = usePathname();
  const { tenant } = useAuth();
  const { data: cezihData } = useCezihStatus();
  const isDemo = cezihData && !cezihData.connected && cezihData.mock;
  const perms = usePermissions();

  return (
    <aside className="hidden lg:flex lg:flex-col lg:w-64 lg:border-r lg:bg-sidebar lg:text-sidebar-foreground">
      <div className="flex items-center gap-2 px-4 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground text-sm font-bold">
          HM
        </div>
        <div className="flex flex-col">
          <span className="text-sm font-semibold leading-tight truncate max-w-[160px]">
            {tenant?.naziv ?? "HM Digital"}
          </span>
          <Badge variant="secondary" className="w-fit text-[10px] px-1.5 mt-0.5">
            {PLAN_TIER[tenant?.plan_tier ?? "trial"] ?? tenant?.plan_tier}
          </Badge>
        </div>
      </div>

      <Separator />

      <nav className="flex-1 px-2 py-3 space-y-1">
        {NAV_ITEMS.filter((item) => !item.perm || perms[item.perm]).map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                  : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground",
              )}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <Separator />

      <div className="px-4 py-3 flex items-center gap-2">
        <span className="text-xs text-muted-foreground">CEZIH</span>
        <div
          className={cn("h-2 w-2 rounded-full", isDemo ? "bg-orange-400" : CEZIH_STATUS_COLORS[tenant?.cezih_status ?? "nepovezano"])}
          title={isDemo ? "Nije povezano (DEMO)" : (tenant?.cezih_status ?? "Nije povezano")}
        />
        <span className="text-xs text-muted-foreground">
          {isDemo ? "Nije povezano (DEMO)" : (CEZIH_STATUS[tenant?.cezih_status ?? "nepovezano"] ?? "Nije povezano")}
        </span>
      </div>
    </aside>
  );
}
