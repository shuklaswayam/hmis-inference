import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Building2, Loader2, AlertTriangle, Bed, Activity, Users, HeartPulse } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import client from '@/api/client'

interface Facility {
  id: string
  name: string
  facility_type: string
  beds_total: number | null
  icu_beds: number | null
  district_name: string
  district_id: string | null
  opd_visits: number | null
  icu_occupancy_pct: number | null
  bed_occupancy_pct: number | null
  emergency_visits: number | null
  maternal_deaths: number | null
  deliveries: number | null
  reported_date: string | null
}

interface FacilitySummary {
  total_facilities: number
  total_districts: number
  total_beds: number
  total_icu_beds: number
  avg_bed_occupancy: number
  avg_icu_occupancy: number
  total_opd_7d: number
  total_emergency_7d: number
}

function OccupancyBar({ value, label }: { value: number | null; label: string }) {
  const pct = value ?? 0
  const color = pct >= 90 ? 'bg-severity-critical' : pct >= 70 ? 'bg-severity-medium' : 'bg-success'
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-caption text-muted-foreground">{label}</span>
        <span className="text-caption font-mono font-semibold text-foreground">{pct.toFixed(1)}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-secondary">
        <div className={cn('h-full rounded-full transition-all', color)} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
    </div>
  )
}

export default function FacilitiesPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const facilitiesQuery = useQuery<Facility[]>({
    queryKey: ['facilities'],
    queryFn: async ({ signal }) => {
      const res = await client.get('/api/v1/facilities/', { signal })
      return (res.data ?? []) as Facility[]
    },
  })

  const summaryQuery = useQuery<FacilitySummary>({
    queryKey: ['facilities', 'summary'],
    queryFn: async ({ signal }) => {
      const res = await client.get('/api/v1/facilities/summary', { signal })
      return res.data as FacilitySummary
    },
  })

  const selected = facilitiesQuery.data?.find((f) => f.id === selectedId) ?? null
  const summary = summaryQuery.data

  return (
    <section className="animate-fade-in">
      <PageHeader
        eyebrow="Workspace"
        title="Facilities"
        description="Hospitals, clinics, and field units with live load, capacity, and risk signals."
        actions={
          <Badge variant="accent" size="sm">
            {facilitiesQuery.data?.length ?? '—'} facilities
          </Badge>
        }
      />

      {/* Summary KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {summaryQuery.isLoading ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20 rounded-lg" />)
        ) : summary ? (
          <>
            <Card className="p-4 border-border/80">
              <div className="flex items-center gap-3">
                <div className="h-9 w-9 rounded-md bg-accent/10 grid place-items-center shrink-0">
                  <Building2 className="h-4 w-4 text-accent" />
                </div>
                <div>
                  <div className="text-display-lg font-semibold text-foreground leading-none">{summary.total_facilities}</div>
                  <div className="text-caption text-muted-foreground mt-1">Facilities</div>
                </div>
              </div>
            </Card>
            <Card className="p-4 border-border/80">
              <div className="flex items-center gap-3">
                <div className="h-9 w-9 rounded-md bg-info/10 grid place-items-center shrink-0">
                  <Bed className="h-4 w-4 text-info" />
                </div>
                <div>
                  <div className="text-display-lg font-semibold text-foreground leading-none">{summary.total_beds}</div>
                  <div className="text-caption text-muted-foreground mt-1">Total Beds</div>
                </div>
              </div>
            </Card>
            <Card className="p-4 border-border/80">
              <div className="flex items-center gap-3">
                <div className="h-9 w-9 rounded-md bg-warning/10 grid place-items-center shrink-0">
                  <Activity className="h-4 w-4 text-warning" />
                </div>
                <div>
                  <div className="text-display-lg font-semibold text-foreground leading-none">{summary.avg_bed_occupancy}%</div>
                  <div className="text-caption text-muted-foreground mt-1">Avg Bed Occ.</div>
                </div>
              </div>
            </Card>
            <Card className="p-4 border-border/80">
              <div className="flex items-center gap-3">
                <div className="h-9 w-9 rounded-md bg-success/10 grid place-items-center shrink-0">
                  <HeartPulse className="h-4 w-4 text-success" />
                </div>
                <div>
                  <div className="text-display-lg font-semibold text-foreground leading-none">{summary.avg_icu_occupancy}%</div>
                  <div className="text-caption text-muted-foreground mt-1">Avg ICU Occ.</div>
                </div>
              </div>
            </Card>
          </>
        ) : null}
      </div>

      {/* Facility list + detail */}
      <div className="grid gap-6 lg:grid-cols-[minmax(340px,35%)_1fr] min-h-[500px]">
        <Card className="overflow-hidden border-border/80">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border/60">
            <h2 className="text-heading-sm font-semibold tracking-tight">All Facilities</h2>
            {facilitiesQuery.isFetching && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
          </div>
          <ScrollArea className="h-[520px]">
            {facilitiesQuery.isLoading ? (
              <div className="p-3 space-y-2">
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-16 rounded-md" />
                ))}
              </div>
            ) : facilitiesQuery.isError ? (
              <div className="p-10 text-center">
                <AlertTriangle className="h-5 w-5 text-severity-critical mx-auto mb-2" />
                <p className="text-body-sm text-muted-foreground">Failed to load facilities</p>
                <Button variant="outline" size="sm" className="mt-3" onClick={() => facilitiesQuery.refetch()}>
                  Retry
                </Button>
              </div>
            ) : (
              <div className="p-2 space-y-1">
                {(facilitiesQuery.data ?? []).map((f) => (
                  <button
                    key={f.id}
                    onClick={() => setSelectedId(f.id)}
                    className={cn(
                      'w-full text-left rounded-md px-3 py-2.5 transition-colors',
                      selectedId === f.id
                        ? 'bg-accent/8 border border-accent/20'
                        : 'hover:bg-secondary/60 border border-transparent',
                    )}
                  >
                    <div className="flex items-center justify-between mb-0.5">
                      <p className="text-body-sm font-medium text-foreground truncate">{f.name}</p>
                      <Badge variant="secondary" size="sm">{f.facility_type}</Badge>
                    </div>
                    <p className="text-caption text-muted-foreground truncate">{f.district_name}</p>
                    {f.bed_occupancy_pct != null && (
                      <div className="mt-1.5">
                        <OccupancyBar value={f.bed_occupancy_pct} label="Bed" />
                      </div>
                    )}
                  </button>
                ))}
              </div>
            )}
          </ScrollArea>
        </Card>

        {/* Detail panel */}
        <Card className="overflow-hidden border-border/80">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border/60">
            <h2 className="text-heading-sm font-semibold tracking-tight">Facility Details</h2>
          </div>
          <ScrollArea className="h-[520px]">
            {!selected ? (
              <div className="flex flex-col items-center justify-center h-full px-8 py-20">
                <Building2 className="h-10 w-10 text-muted-foreground/30 mb-4" />
                <h3 className="text-heading-sm font-semibold text-foreground mb-1">Select a facility</h3>
                <p className="text-body-sm text-muted-foreground text-center max-w-[260px]">
                  Choose a facility from the list to view its metrics, capacity, and risk signals.
                </p>
              </div>
            ) : (
              <div className="p-6 space-y-6 animate-fade-in">
                <div>
                  <h3 className="text-heading-sm font-semibold text-foreground mb-1">{selected.name}</h3>
                  <p className="text-body-sm text-muted-foreground">{selected.district_name} · {selected.facility_type}</p>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="rounded-lg border border-border/60 p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <Bed className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="text-caption text-muted-foreground">Beds</span>
                    </div>
                    <span className="text-heading-sm font-semibold text-foreground">{selected.beds_total ?? '—'}</span>
                  </div>
                  <div className="rounded-lg border border-border/60 p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <Activity className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="text-caption text-muted-foreground">ICU Beds</span>
                    </div>
                    <span className="text-heading-sm font-semibold text-foreground">{selected.icu_beds ?? '—'}</span>
                  </div>
                </div>

                <div className="space-y-3">
                  <OccupancyBar value={selected.bed_occupancy_pct} label="Bed Occupancy" />
                  <OccupancyBar value={selected.icu_occupancy_pct} label="ICU Occupancy" />
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div className="rounded-lg border border-border/60 p-3 text-center">
                    <Users className="h-4 w-4 text-muted-foreground mx-auto mb-1" />
                    <div className="text-body-sm font-semibold text-foreground">{selected.opd_visits ?? 0}</div>
                    <div className="text-caption text-muted-foreground">OPD Visits</div>
                  </div>
                  <div className="rounded-lg border border-border/60 p-3 text-center">
                    <Activity className="h-4 w-4 text-muted-foreground mx-auto mb-1" />
                    <div className="text-body-sm font-semibold text-foreground">{selected.emergency_visits ?? 0}</div>
                    <div className="text-caption text-muted-foreground">Emergency</div>
                  </div>
                  <div className="rounded-lg border border-border/60 p-3 text-center">
                    <HeartPulse className="h-4 w-4 text-muted-foreground mx-auto mb-1" />
                    <div className="text-body-sm font-semibold text-foreground">{selected.deliveries ?? 0}</div>
                    <div className="text-caption text-muted-foreground">Deliveries</div>
                  </div>
                </div>

                {selected.reported_date && (
                  <p className="text-caption text-muted-foreground">
                    Last reported: {new Date(selected.reported_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                  </p>
                )}
              </div>
            )}
          </ScrollArea>
        </Card>
      </div>
    </section>
  )
}
