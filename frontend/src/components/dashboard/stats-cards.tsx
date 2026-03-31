"use client"

import Link from "next/link"
import { CalendarDays, Users, CalendarCheck, UserPlus } from "lucide-react"

import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useDashboardStats } from "@/lib/hooks/use-dashboard"
import { useCezihConnectionDisplay } from "@/lib/hooks/use-cezih"

export function StatsCards() {
  const { data: stats, isLoading } = useDashboardStats()
  const cezih = useCezihConnectionDisplay()

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}>
            <CardContent className="p-6">
              <Skeleton className="h-4 w-24 mb-2" />
              <Skeleton className="h-8 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  if (!stats) return null

  const cards = [
    {
      label: "Termini danas",
      value: stats.danas_termini,
      icon: CalendarDays,
      href: "/termini",
    },
    {
      label: "Ukupno pacijenata",
      value: stats.ukupno_pacijenti,
      icon: Users,
      href: "/pacijenti",
    },
    {
      label: "Termini ovaj tjedan",
      value: stats.ovaj_tjedan_termini,
      icon: CalendarCheck,
      href: "/termini",
    },
    {
      label: "Novi pacijenti (mjesec)",
      value: stats.novi_pacijenti_mjesec,
      icon: UserPlus,
      href: "/pacijenti",
    },
  ]

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {cards.map((card) => (
        <Link key={card.label} href={card.href}>
          <Card className="hover:bg-accent/50 transition-colors cursor-pointer">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-muted-foreground">
                  {card.label}
                </p>
                <card.icon className="h-4 w-4 text-muted-foreground" />
              </div>
              <p className="text-2xl font-bold mt-2">{card.value}</p>
            </CardContent>
          </Card>
        </Link>
      ))}

      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-muted-foreground">
              CEZIH status
            </p>
            <div className={`h-2.5 w-2.5 rounded-full ${cezih.dotColor}`} />
          </div>
          <p className="text-2xl font-bold mt-2">{cezih.label}</p>
          {cezih.connectedDoctor && (
            <p className="text-xs text-muted-foreground mt-1">
              {cezih.connectedDoctor}
              {cezih.connectedClinic && <> via {cezih.connectedClinic}</>}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
