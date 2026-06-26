import { useQuery } from '@tanstack/react-query'
import { FileText, Download, Calendar, Loader2, AlertTriangle } from 'lucide-react'

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
  facility_name: string
  district_name: string
  what_is_happening: string
  created_at: string
}

const REPORT_TYPES = [
  {
    name: 'Daily Alert Summary',
    description: 'All alerts from the past 24 hours with severity breakdown and facility list.',
    frequency: 'Daily',
    format: 'PDF',
  },
  {
    name: 'Weekly District Digest',
    description: 'Aggregated metrics, trend analysis, and top alerts per district.',
    frequency: 'Weekly',
    format: 'PDF',
  },
  {
    name: 'Facility Performance Report',
    description: 'Bed occupancy, ICU utilization, and OPD visit trends across facilities.',
    frequency: 'Monthly',
    format: 'CSV',
  },
  {
    name: 'Disease Outbreak Forecast',
    description: '7-day disease case forecasts with confidence intervals by district.',
    frequency: 'Weekly',
    format: 'PDF',
  },
  {
    name: 'Maternal Health Monitor',
    description: 'Maternal deaths, deliveries, and facility-level maternal health indicators.',
    frequency: 'Monthly',
    format: 'PDF',
  },
]

export default function ReportsPage() {
  const alertsQuery = useQuery<Alert[]>({
    queryKey: ['alerts', 'reports'],
    queryFn: async ({ signal }) => {
      const res = await client.get('/api/v1/alerts/', { signal })
      return (res.data ?? []) as Alert[]
    },
  })

  const alerts = alertsQuery.data ?? []
  const criticalCount = alerts.filter((a) => a.severity === 'HIGH').length
  const warningCount = alerts.filter((a) => a.severity === 'MEDIUM').length

  return (
    <section className="animate-fade-in">
      <PageHeader
        eyebrow="Workspace"
        title="Reports"
        description="Scheduled exports, executive digests, and ad-hoc queries."
        actions={
          <Button variant="outline" size="sm">
            <Download className="h-3.5 w-3.5 mr-1.5" />
            Export All
          </Button>
        }
      />

      {/* Quick summary */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <Card className="p-4 border-border/80">
          <div className="text-caption text-muted-foreground mb-1">Total Alerts</div>
          <div className="text-heading-md font-semibold text-foreground">{alerts.length}</div>
        </Card>
        <Card className="p-4 border-border/80">
          <div className="text-caption text-muted-foreground mb-1">Critical</div>
          <div className="text-heading-md font-semibold text-severity-critical">{criticalCount}</div>
        </Card>
        <Card className="p-4 border-border/80">
          <div className="text-caption text-muted-foreground mb-1">Warning</div>
          <div className="text-heading-md font-semibold text-severity-medium">{warningCount}</div>
        </Card>
        <Card className="p-4 border-border/80">
          <div className="text-caption text-muted-foreground mb-1">Report Types</div>
          <div className="text-heading-md font-semibold text-foreground">{REPORT_TYPES.length}</div>
        </Card>
      </div>

      {/* Report types grid */}
      <h2 className="text-subheading font-semibold text-foreground mb-4">Available Reports</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
        {REPORT_TYPES.map((report) => (
          <Card key={report.name} className="p-5 border-border/80 hover:shadow-soft-md transition-shadow">
            <div className="flex items-start gap-3 mb-3">
              <div className="h-9 w-9 rounded-md bg-accent/10 grid place-items-center shrink-0">
                <FileText className="h-4 w-4 text-accent" />
              </div>
              <div className="min-w-0">
                <h3 className="text-body-sm font-semibold text-foreground">{report.name}</h3>
                <p className="text-caption text-muted-foreground mt-0.5">{report.description}</p>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Badge variant="secondary" size="sm">{report.frequency}</Badge>
                <Badge variant="outline" size="sm">{report.format}</Badge>
              </div>
              <Button variant="ghost" size="sm">
                <Download className="h-3.5 w-3.5" />
              </Button>
            </div>
          </Card>
        ))}
      </div>

      {/* Recent alerts table */}
      <Card className="border-border/80 overflow-hidden">
        <div className="px-4 py-3 border-b border-border/60 flex items-center justify-between">
          <h2 className="text-subheading font-semibold tracking-tight">Recent Alert Data</h2>
          {alertsQuery.isFetching && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
        </div>
        {alertsQuery.isLoading ? (
          <div className="p-4 space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 rounded-md" />
            ))}
          </div>
        ) : alertsQuery.isError ? (
          <div className="p-8 text-center">
            <AlertTriangle className="h-5 w-5 text-severity-critical mx-auto mb-2" />
            <p className="text-body-sm text-muted-foreground">Failed to load alert data</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-border/60">
                  <th className="px-4 py-2.5 text-caption font-semibold text-muted-foreground">Severity</th>
                  <th className="px-4 py-2.5 text-caption font-semibold text-muted-foreground">Facility</th>
                  <th className="px-4 py-2.5 text-caption font-semibold text-muted-foreground">District</th>
                  <th className="px-4 py-2.5 text-caption font-semibold text-muted-foreground">Summary</th>
                  <th className="px-4 py-2.5 text-caption font-semibold text-muted-foreground">Date</th>
                </tr>
              </thead>
              <tbody>
                {alerts.slice(0, 10).map((alert) => (
                  <tr key={alert.id} className="border-b border-border/40 hover:bg-secondary/30 transition-colors">
                    <td className="px-4 py-2.5">
                      <Badge
                        variant={alert.severity === 'HIGH' ? 'critical' : alert.severity === 'MEDIUM' ? 'warning' : 'secondary'}
                        size="sm"
                      >
                        {alert.severity}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5 text-body-sm text-foreground">{alert.facility_name || '—'}</td>
                    <td className="px-4 py-2.5 text-body-sm text-muted-foreground">{alert.district_name}</td>
                    <td className="px-4 py-2.5 text-body-sm text-muted-foreground max-w-[200px] truncate">
                      {alert.what_is_happening || '—'}
                    </td>
                    <td className="px-4 py-2.5 text-caption text-muted-foreground whitespace-nowrap">
                      {alert.created_at ? new Date(alert.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </section>
  )
}
