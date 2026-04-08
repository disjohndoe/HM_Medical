"use client"

import Link from "next/link"
import { Activity, FileText, Clock } from "lucide-react"

import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useCezihDashboardStats } from "@/lib/hooks/use-cezih"

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "Nema operacija"
  const now = new Date()
  const date = new Date(dateStr)
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000)

  if (seconds < 60) return "upravo sada"
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `prije ${minutes} min`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `prije ${hours} h`
  const days = Math.floor(hours / 24)
  return `prije ${days} d`
}

export function CezihDashboardWidgets() {
  const { data: stats, isLoading } = useCezihDashboardStats()

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
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
      label: "Danas CEZIH",
      value: stats.danas_operacije,
      icon: Activity,
      href: "/cezih",
    },
    {
      label: "Otvoreni CEZIH nalazi",
      value: stats.neposlani_nalazi,
      icon: FileText,
      href: "/cezih-nalazi",
    },
    {
      label: "Zadnja sinkronizacija",
      value: timeAgo(stats.zadnja_operacija),
      icon: Clock,
      href: "/cezih",
    },
  ]

  return (
    <div className="grid gap-4 md:grid-cols-3">
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
    </div>
  )
}
