import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Database, Loader2, AlertTriangle, ChevronLeft, ChevronRight } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import client from '@/api/client'

interface DiseaseReportRow {
  id: string
  facility_id: string
  facility_name: string
  district_name: string
  disease_name: string
  reported_date: string
  case_count: number
  deaths: number
  age_group: string | null
  severity: string | null
  created_at: string
}

interface FacilityMetricsRow {
  id: string
  facility_id: string
  facility_name: string
  district_name: string
  reported_date: string
  opd_visits: number
  icu_occupancy_pct: number | null
  bed_occupancy_pct: number | null
  emergency_visits: number
  maternal_deaths: number
  deliveries: number
  medicine_days_remaining: number | null
  staff_attendance_pct: number | null
  created_at: string
}

const PAGE_SIZE = 50

export default function RawDataPage() {
  const [tab, setTab] = useState<'disease' | 'metrics'>('disease')
  const [page, setPage] = useState(0)
  const offset = page * PAGE_SIZE

  const diseaseQuery = useQuery({
    queryKey: ['raw-disease-reports', offset],
    queryFn: async ({ signal }) => {
      const res = await client.get('/api/v1/ingest/disease_reports', {
        params: { limit: PAGE_SIZE, offset },
        signal,
      })
      return res.data as { total: number; data: DiseaseReportRow[] }
    },
    enabled: tab === 'disease',
    refetchInterval: 10000,
  })

  const metricsQuery = useQuery({
    queryKey: ['raw-facility-metrics', offset],
    queryFn: async ({ signal }) => {
      const res = await client.get('/api/v1/ingest/facility_metrics', {
        params: { limit: PAGE_SIZE, offset },
        signal,
      })
      return res.data as { total: number; data: FacilityMetricsRow[] }
    },
    enabled: tab === 'metrics',
    refetchInterval: 10000,
  })

  const data = tab === 'disease' ? diseaseQuery.data : metricsQuery.data
  const isLoading = tab === 'disease' ? diseaseQuery.isLoading : metricsQuery.isLoading
  const isError = tab === 'disease' ? diseaseQuery.isError : metricsQuery.isError
  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0

  return (
    <section className="animate-fade-in">
      <PageHeader
        eyebrow="Data"
        title="Raw Data"
        description="Inspect the underlying disease reports and facility metrics feeding the inference engine."
        actions={
          <Badge variant="accent" size="sm">
            {data?.total ?? '—'} rows
          </Badge>
        }
      />

      {/* Tab bar */}
      <div className="flex gap-1 p-1 rounded-lg bg-secondary/40 w-fit mb-6">
        <button
          onClick={() => { setTab('disease'); setPage(0) }}
          className={cn(
            'px-4 py-1.5 rounded-md text-body-sm font-medium transition-colors',
            tab === 'disease'
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          Disease Reports
        </button>
        <button
          onClick={() => { setTab('metrics'); setPage(0) }}
          className={cn(
            'px-4 py-1.5 rounded-md text-body-sm font-medium transition-colors',
            tab === 'metrics'
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          Facility Metrics
        </button>
      </div>

      {/* Error state */}
      {isError && (
        <Card className="p-8 text-center border-border/80">
          <AlertTriangle className="h-5 w-5 text-severity-critical mx-auto mb-2" />
          <p className="text-body-sm text-muted-foreground">Failed to load data</p>
          <Button variant="outline" size="sm" className="mt-3" onClick={() => tab === 'disease' ? diseaseQuery.refetch() : metricsQuery.refetch()}>
            Retry
          </Button>
        </Card>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-12 rounded-md" />
          ))}
        </div>
      )}

      {/* Table */}
      {!isLoading && !isError && data && (
        <Card className="overflow-hidden border-border/80">
          <div className="overflow-x-auto">
            <table className="w-full text-body-sm">
              <thead>
                <tr className="border-b border-border/60 text-caption text-muted-foreground uppercase tracking-wider">
                  {tab === 'disease' ? (
                    <>
                      <th className="text-left px-4 py-2.5 font-medium">Reported</th>
                      <th className="text-left px-4 py-2.5 font-medium">Ingested</th>
                      <th className="text-left px-4 py-2.5 font-medium">Facility</th>
                      <th className="text-left px-4 py-2.5 font-medium">District</th>
                      <th className="text-left px-4 py-2.5 font-medium">Disease</th>
                      <th className="text-right px-4 py-2.5 font-medium">Cases</th>
                      <th className="text-right px-4 py-2.5 font-medium">Deaths</th>
                      <th className="text-left px-4 py-2.5 font-medium">Age Group</th>
                      <th className="text-left px-4 py-2.5 font-medium">Severity</th>
                    </>
                  ) : (
                    <>
                      <th className="text-left px-4 py-2.5 font-medium">Reported</th>
                      <th className="text-left px-4 py-2.5 font-medium">Ingested</th>
                      <th className="text-left px-4 py-2.5 font-medium">Facility</th>
                      <th className="text-left px-4 py-2.5 font-medium">District</th>
                      <th className="text-right px-4 py-2.5 font-medium">OPD</th>
                      <th className="text-right px-4 py-2.5 font-medium">ICU %</th>
                      <th className="text-right px-4 py-2.5 font-medium">Bed %</th>
                      <th className="text-right px-4 py-2.5 font-medium">Emergency</th>
                      <th className="text-right px-4 py-2.5 font-medium">Deliveries</th>
                      <th className="text-right px-4 py-2.5 font-medium">Med Days</th>
                      <th className="text-right px-4 py-2.5 font-medium">Staff %</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {data.data.map((row) => (
                  <tr key={row.id} className="border-b border-border/30 hover:bg-secondary/30 transition-colors">
                    {tab === 'disease' ? (
                      <>
                        <td className="px-4 py-2 font-mono text-caption text-muted-foreground whitespace-nowrap">
                          {row.reported_date}
                        </td>
                        <td className="px-4 py-2 font-mono text-caption text-accent whitespace-nowrap">
                          {new Date((row as DiseaseReportRow).created_at).toLocaleString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
                        </td>
                        <td className="px-4 py-2 font-medium text-foreground truncate max-w-[200px]">
                          {(row as DiseaseReportRow).facility_name}
                        </td>
                        <td className="px-4 py-2 text-muted-foreground">{(row as DiseaseReportRow).district_name}</td>
                        <td className="px-4 py-2">
                          <Badge variant="secondary" size="sm">{(row as DiseaseReportRow).disease_name}</Badge>
                        </td>
                        <td className="px-4 py-2 text-right font-mono font-semibold text-foreground">{(row as DiseaseReportRow).case_count}</td>
                        <td className="px-4 py-2 text-right font-mono text-muted-foreground">{(row as DiseaseReportRow).deaths}</td>
                        <td className="px-4 py-2 text-muted-foreground">{(row as DiseaseReportRow).age_group ?? '—'}</td>
                        <td className="px-4 py-2">
                          {(row as DiseaseReportRow).severity ? (
                            <Badge variant={
                              (row as DiseaseReportRow).severity === 'critical' ? 'critical'
                              : (row as DiseaseReportRow).severity === 'high' ? 'high'
                              : (row as DiseaseReportRow).severity === 'medium' ? 'medium'
                              : 'low'
                            } size="sm">{(row as DiseaseReportRow).severity}</Badge>
                          ) : <span className="text-muted-foreground/50">—</span>}
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="px-4 py-2 font-mono text-caption text-muted-foreground whitespace-nowrap">
                          {row.reported_date}
                        </td>
                        <td className="px-4 py-2 font-mono text-caption text-accent whitespace-nowrap">
                          {new Date((row as FacilityMetricsRow).created_at).toLocaleString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
                        </td>
                        <td className="px-4 py-2 font-medium text-foreground truncate max-w-[200px]">
                          {(row as FacilityMetricsRow).facility_name}
                        </td>
                        <td className="px-4 py-2 text-muted-foreground">{(row as FacilityMetricsRow).district_name}</td>
                        <td className="px-4 py-2 text-right font-mono text-foreground">{(row as FacilityMetricsRow).opd_visits}</td>
                        <td className="px-4 py-2 text-right font-mono">
                          <span className={cn(
                            (row as FacilityMetricsRow).icu_occupancy_pct != null && (row as FacilityMetricsRow).icu_occupancy_pct! >= 90
                              ? 'text-severity-critical font-semibold'
                              : 'text-muted-foreground'
                          )}>
                            {(row as FacilityMetricsRow).icu_occupancy_pct?.toFixed(1) ?? '—'}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-right font-mono">
                          <span className={cn(
                            (row as FacilityMetricsRow).bed_occupancy_pct != null && (row as FacilityMetricsRow).bed_occupancy_pct! >= 90
                              ? 'text-severity-critical font-semibold'
                              : 'text-muted-foreground'
                          )}>
                            {(row as FacilityMetricsRow).bed_occupancy_pct?.toFixed(1) ?? '—'}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-right font-mono text-muted-foreground">{(row as FacilityMetricsRow).emergency_visits}</td>
                        <td className="px-4 py-2 text-right font-mono text-muted-foreground">{(row as FacilityMetricsRow).deliveries}</td>
                        <td className="px-4 py-2 text-right font-mono text-muted-foreground">
                          {(row as FacilityMetricsRow).medicine_days_remaining?.toFixed(0) ?? '—'}
                        </td>
                        <td className="px-4 py-2 text-right font-mono text-muted-foreground">
                          {(row as FacilityMetricsRow).staff_attendance_pct?.toFixed(1) ?? '—'}
                        </td>
                      </>
                    )}
                  </tr>
                ))}
                {data.data.length === 0 && (
                  <tr>
                    <td colSpan={tab === 'disease' ? 9 : 11} className="px-4 py-12 text-center text-muted-foreground">
                      No data found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-4 py-2.5 border-t border-border/60">
              <span className="text-caption text-muted-foreground">
                Page {page + 1} of {totalPages}
              </span>
              <div className="flex gap-1">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page === 0}
                  onClick={() => setPage((p) => p - 1)}
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages - 1}
                  onClick={() => setPage((p) => p + 1)}
                >
                  <ChevronRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          )}
        </Card>
      )}
    </section>
  )
}
