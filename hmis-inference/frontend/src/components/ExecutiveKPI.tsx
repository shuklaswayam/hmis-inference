import { useQuery } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'

import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import client from '@/api/client'

interface KpiItem {
  label: string
  value: string
  change: string
  trend: 'up' | 'stable' | 'down'
  variant: 'critical' | 'warning' | 'info' | 'success'
  icon: React.ReactNode
}

function Sparkline({ variant, trend }: { variant: string; trend: string }) {
  const colorMap: Record<string, string> = {
    critical: 'hsl(var(--severity-critical))',
    warning: 'hsl(var(--severity-medium))',
    info: 'hsl(var(--info))',
    success: 'hsl(var(--success))',
  }
  const paths: Record<string, string> = {
    up: 'M0,18 L6,14 L12,16 L18,10 L24,12 L30,6 L36,8 L42,4 L48,2',
    stable: 'M0,10 L6,10 L12,10 L18,10 L24,10 L30,10 L36,10 L42,10 L48,10',
    down: 'M0,2 L6,6 L12,4 L18,10 L24,8 L30,14 L36,12 L42,16 L48,18',
  }

  return (
    <svg width="48" height="20" viewBox="0 0 48 20" className="shrink-0" fill="none">
      <path d={paths[trend] || paths.stable} stroke={colorMap[variant] || colorMap.info} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function buildKpis(data: unknown[]): KpiItem[] {
  const alerts = data as { severity?: string; [k: string]: unknown }[]
  const total = alerts.length
  const critical = alerts.filter((a) => a.severity === 'HIGH').length

  return [
    {
      label: 'Total Alerts',
      value: String(total),
      change: total > 0 ? `+${total}` : '0',
      trend: total > 5 ? 'up' : 'stable',
      variant: 'critical',
      icon: (
        <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
        </svg>
      ),
    },
    {
      label: 'Critical Alerts',
      value: String(critical),
      change: critical > 0 ? `+${critical}` : '0',
      trend: critical > 2 ? 'up' : 'stable',
      variant: 'warning',
      icon: (
        <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 9v3.75m-3.75 3.75h1.5a2.25 2.25 0 002.25-2.25v-1.5m0 0V9m0 3.75H7.5m9 0h1.5a2.25 2.25 0 002.25-2.25v-1.5m0 0V9m0 3.75H18" />
        </svg>
      ),
    },
    {
      label: 'Active Investigations',
      value: String(total),
      change: total > 0 ? `+${total}` : '0',
      trend: 'up',
      variant: 'info',
      icon: (
        <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
          <path d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5" />
        </svg>
      ),
    },
    {
      label: 'Facilities Monitored',
      value: '—',
      change: '0',
      trend: 'stable',
      variant: 'success',
      icon: (
        <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
          <path d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21" />
        </svg>
      ),
    },
  ]
}

export function ExecutiveKPI() {
  const { data, isLoading } = useQuery({
    queryKey: ['alerts', 'kpi'],
    queryFn: async ({ signal }) => {
      const res = await client.get('/api/v1/alerts/', { signal })
      return res.data ?? []
    },
  })

  const kpis = isLoading ? null : buildKpis(data)

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {isLoading
        ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28 rounded-lg" />)
        : kpis?.map((kpi) => (
            <Card key={kpi.label} className="p-5 border-border/80 hover:shadow-soft-md transition-all duration-200">
              <div className="flex items-start justify-between mb-4">
                <div className={`w-10 h-10 rounded-lg grid place-items-center shrink-0 bg-${kpi.variant}/10 text-${kpi.variant}`}>
                  {kpi.icon}
                </div>
                <Sparkline variant={kpi.variant} trend={kpi.trend} />
              </div>
              <div>
                <div className="text-display-lg font-semibold tracking-tight text-foreground leading-none mb-1">
                  {kpi.value}
                </div>
                <div className="flex items-center gap-2 text-body-sm text-muted-foreground">
                  <span>{kpi.label}</span>
                  <span className="w-1 h-1 rounded-full bg-border" />
                  <span className="font-medium text-foreground">{kpi.change}</span>
                </div>
              </div>
            </Card>
          ))}
    </div>
  )
}
