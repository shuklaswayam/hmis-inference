import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { LineChart as LineChartIcon, Loader2, AlertTriangle } from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, PieChart, Pie, Cell, Legend,
} from 'recharts'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import client from '@/api/client'

interface Alert {
  id: string
  severity: string
  district_name: string
  created_at: string
  confidence_score: number
}

const SEVERITY_COLORS: Record<string, string> = {
  HIGH: 'hsl(var(--severity-critical))',
  MEDIUM: 'hsl(var(--severity-medium))',
  LOW: 'hsl(var(--severity-low))',
}

const TABS = ['Overview', 'By District', 'Trends'] as const

export default function AnalyticsPage() {
  const [tab, setTab] = useState<typeof TABS[number]>('Overview')

  const alertsQuery = useQuery<Alert[]>({
    queryKey: ['alerts', 'analytics'],
    queryFn: async ({ signal }) => {
      const res = await client.get('/api/v1/alerts/', { signal })
      return (res.data ?? []) as Alert[]
    },
  })

  const alerts = alertsQuery.data ?? []

  // Compute severity distribution
  const severityData = [
    { name: 'Critical', value: alerts.filter((a) => a.severity === 'HIGH').length, color: SEVERITY_COLORS.HIGH },
    { name: 'Warning', value: alerts.filter((a) => a.severity === 'MEDIUM').length, color: SEVERITY_COLORS.MEDIUM },
    { name: 'Low', value: alerts.filter((a) => a.severity === 'LOW').length, color: SEVERITY_COLORS.LOW },
  ]

  // Compute alerts by district
  const districtMap = new Map<string, { high: number; medium: number; low: number }>()
  alerts.forEach((a) => {
    const name = a.district_name || 'Unknown'
    if (!districtMap.has(name)) districtMap.set(name, { high: 0, medium: 0, low: 0 })
    const bucket = districtMap.get(name)!
    if (a.severity === 'HIGH') bucket.high++
    else if (a.severity === 'MEDIUM') bucket.medium++
    else bucket.low++
  })
  const districtData = Array.from(districtMap.entries()).map(([name, counts]) => ({
    name: name.length > 12 ? name.slice(0, 12) + '…' : name,
    fullName: name,
    ...counts,
  }))

  // Timeline data (last 7 days)
  const timelineData = (() => {
    const now = new Date()
    const days: { date: string; count: number }[] = []
    for (let i = 6; i >= 0; i--) {
      const d = new Date(now)
      d.setDate(d.getDate() - i)
      const label = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
      const dayStr = d.toISOString().slice(0, 10)
      const count = alerts.filter((a) => a.created_at?.startsWith(dayStr)).length
      days.push({ date: label, count })
    }
    return days
  })()

  return (
    <section className="animate-fade-in">
      <PageHeader
        eyebrow="Analytics"
        title="Analytics"
        description="Trend lines, comparisons, and forecasts for every metric that matters."
        actions={
          <Badge variant="accent" size="sm">
            {alerts.length} data points
          </Badge>
        }
      />

      {/* Tabs */}
      <div className="flex gap-1 bg-secondary/60 rounded-lg p-0.5 mb-6 w-fit">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              'px-4 py-1.5 text-body-sm font-medium rounded-md transition-all',
              tab === t
                ? 'bg-background text-foreground shadow-soft-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {alertsQuery.isLoading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-64 rounded-lg" />
          ))}
        </div>
      ) : alertsQuery.isError ? (
        <div className="p-10 text-center">
          <AlertTriangle className="h-5 w-5 text-severity-critical mx-auto mb-2" />
          <p className="text-body-sm text-muted-foreground">Failed to load analytics data</p>
          <Button variant="outline" size="sm" className="mt-3" onClick={() => alertsQuery.refetch()}>
            Retry
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Severity Distribution */}
          <Card className="p-6 border-border/80">
            <h3 className="text-subheading font-semibold text-foreground mb-4">Severity Distribution</h3>
            {alerts.length === 0 ? (
              <p className="text-body-sm text-muted-foreground text-center py-8">No alert data available</p>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie
                    data={severityData}
                    cx="50%"
                    cy="50%"
                    innerRadius={55}
                    outerRadius={85}
                    paddingAngle={3}
                    dataKey="value"
                  >
                    {severityData.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      background: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                  />
                  <Legend
                    formatter={(value: string) => <span className="text-body-sm text-foreground">{value}</span>}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </Card>

          {/* Alerts by District */}
          <Card className="p-6 border-border/80">
            <h3 className="text-subheading font-semibold text-foreground mb-4">Alerts by District</h3>
            {districtData.length === 0 ? (
              <p className="text-body-sm text-muted-foreground text-center py-8">No district data available</p>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={districtData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} />
                  <YAxis tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} />
                  <Tooltip
                    contentStyle={{
                      background: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                  />
                  <Legend formatter={(value: string) => <span className="text-body-sm text-foreground">{value}</span>} />
                  <Bar dataKey="high" name="Critical" fill={SEVERITY_COLORS.HIGH} radius={[4, 4, 0, 0]} />
                  <Bar dataKey="medium" name="Warning" fill={SEVERITY_COLORS.MEDIUM} radius={[4, 4, 0, 0]} />
                  <Bar dataKey="low" name="Low" fill={SEVERITY_COLORS.LOW} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </Card>

          {/* Timeline */}
          <Card className="p-6 border-border/80 lg:col-span-2">
            <h3 className="text-subheading font-semibold text-foreground mb-4">Alert Timeline (7 Days)</h3>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={timelineData}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} />
                <YAxis tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} />
                <Tooltip
                  contentStyle={{
                    background: 'hsl(var(--card))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '8px',
                    fontSize: '12px',
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="count"
                  name="Alerts"
                  stroke="hsl(var(--accent))"
                  strokeWidth={2}
                  dot={{ fill: 'hsl(var(--accent))', r: 4 }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </Card>

          {/* Confidence Distribution */}
          <Card className="p-6 border-border/80 lg:col-span-2">
            <h3 className="text-subheading font-semibold text-foreground mb-4">Confidence Score Distribution</h3>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart
                data={(() => {
                  const buckets = [
                    { range: '0-20%', count: 0 },
                    { range: '20-40%', count: 0 },
                    { range: '40-60%', count: 0 },
                    { range: '60-80%', count: 0 },
                    { range: '80-100%', count: 0 },
                  ]
                  alerts.forEach((a) => {
                    const pct = (a.confidence_score || 0) * 100
                    const idx = Math.min(Math.floor(pct / 20), 4)
                    buckets[idx].count++
                  })
                  return buckets
                })()}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="range" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} />
                <YAxis tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} />
                <Tooltip
                  contentStyle={{
                    background: 'hsl(var(--card))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '8px',
                    fontSize: '12px',
                  }}
                />
                <Bar dataKey="count" name="Alerts" fill="hsl(var(--accent))" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </div>
      )}
    </section>
  )
}
