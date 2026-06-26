import { useQuery } from '@tanstack/react-query'
import { useState, useEffect } from 'react'
import { Search, AlertTriangle, Loader2, Clock, ArrowRight } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import client from '@/api/client'

interface Alert {
  id: string
  severity: string
  facility_name: string
  district_name: string
  what_is_happening: string
  why_it_happening: string
  recommended_action: string
  confidence_score: number
  llm_generated: boolean
  created_at: string
  rule_name: string
  rule_flags: unknown
}

function timeAgo(dateStr: string) {
  if (!dateStr) return ''
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function getSeverityMeta(severity: string) {
  switch (severity) {
    case 'HIGH':
      return { label: 'Critical', variant: 'critical' as const, dot: 'bg-severity-critical' }
    case 'MEDIUM':
      return { label: 'Warning', variant: 'warning' as const, dot: 'bg-severity-medium' }
    case 'LOW':
      return { label: 'Low', variant: 'low' as const, dot: 'bg-severity-low' }
    default:
      return { label: severity, variant: 'secondary' as const, dot: 'bg-muted-foreground' }
  }
}

export default function InvestigationsPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const alertsQuery = useQuery<Alert[]>({
    queryKey: ['alerts', 'investigations'],
    queryFn: async ({ signal }) => {
      const res = await client.get('/api/v1/alerts/', { signal })
      return (res.data ?? []) as Alert[]
    },
  })

  const selected = alertsQuery.data?.find((a) => a.id === selectedId) ?? null

  useEffect(() => {
    if (!selectedId && alertsQuery.data && alertsQuery.data.length > 0) {
      setSelectedId(alertsQuery.data[0].id)
    }
  }, [alertsQuery.data, selectedId])

  return (
    <section className="animate-fade-in">
      <PageHeader
        eyebrow="Workspace"
        title="Investigations"
        description="Open cases, hypotheses, and AI-assisted root-cause analyses across districts."
        actions={
          <Badge variant="accent" size="sm">
            {alertsQuery.data?.length ?? '—'} active cases
          </Badge>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(340px,35%)_1fr] min-h-[600px]">
        {/* Case list */}
        <Card className="overflow-hidden border-border/80">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border/60">
            <div className="flex items-baseline gap-2">
              <h2 className="text-heading-sm font-semibold tracking-tight">Cases</h2>
            </div>
            {alertsQuery.isFetching && (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
            )}
          </div>
          <ScrollArea className="h-[560px]">
            {alertsQuery.isLoading ? (
              <div className="p-3 space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="rounded-md border border-border/60 p-3 space-y-2">
                    <div className="flex items-center gap-2">
                      <Skeleton className="h-4 w-16" />
                      <Skeleton className="h-3 w-24" />
                    </div>
                    <Skeleton className="h-3 w-full" />
                    <Skeleton className="h-3 w-2/3" />
                  </div>
                ))}
              </div>
            ) : alertsQuery.isError ? (
              <div className="p-10 text-center">
                <AlertTriangle className="h-5 w-5 text-severity-critical mx-auto mb-2" />
                <p className="text-body-sm text-muted-foreground">Failed to load cases</p>
                <Button variant="outline" size="sm" className="mt-3" onClick={() => alertsQuery.refetch()}>
                  Retry
                </Button>
              </div>
            ) : (alertsQuery.data ?? []).length === 0 ? (
              <div className="p-10 text-center">
                <Search className="h-8 w-8 text-muted-foreground/40 mx-auto mb-3" />
                <p className="text-body-sm text-muted-foreground">No open investigations</p>
              </div>
            ) : (
              <div className="p-2 space-y-1">
                {(alertsQuery.data ?? []).map((alert) => {
                  const sev = getSeverityMeta(alert.severity)
                  const isActive = selectedId === alert.id
                  return (
                    <button
                      key={alert.id}
                      onClick={() => setSelectedId(alert.id)}
                      className={cn(
                        'w-full text-left rounded-md px-3 py-2.5 transition-colors',
                        isActive
                          ? 'bg-accent/8 border border-accent/20'
                          : 'hover:bg-secondary/60 border border-transparent',
                      )}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <Badge variant={sev.variant} size="sm">{sev.label}</Badge>
                        <span className="text-caption text-muted-foreground">{alert.rule_name}</span>
                      </div>
                      <p className="text-body-sm font-medium text-foreground truncate">
                        {alert.facility_name || 'Unknown Facility'}
                      </p>
                      <p className="text-caption text-muted-foreground mt-0.5 truncate">
                        {alert.district_name} · {timeAgo(alert.created_at)}
                      </p>
                    </button>
                  )
                })}
              </div>
            )}
          </ScrollArea>
        </Card>

        {/* Investigation detail */}
        <Card className="overflow-hidden border-border/80">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border/60">
            <div className="flex items-baseline gap-2">
              <h2 className="text-heading-sm font-semibold tracking-tight">Root Cause Analysis</h2>
              {selected && (
                <span className="text-caption text-muted-foreground">
                  Alert #{selected.id}
                </span>
              )}
            </div>
            {selected && (
              <Badge variant={getSeverityMeta(selected.severity).variant} size="sm">
                {getSeverityMeta(selected.severity).label}
              </Badge>
            )}
          </div>
          <ScrollArea className="h-[560px]">
            {!selected ? (
              <div className="flex flex-col items-center justify-center h-full px-8 py-20">
                <Search className="h-10 w-10 text-muted-foreground/30 mb-4" />
                <h3 className="text-heading-sm font-semibold text-foreground mb-1">Select a case</h3>
                <p className="text-body-sm text-muted-foreground text-center max-w-[260px]">
                  Choose an investigation from the list to view the full root cause analysis and recommended actions.
                </p>
              </div>
            ) : (
              <div className="p-6 space-y-6 animate-fade-in">
                {/* Header */}
                <div>
                  <h3 className="text-heading-sm font-semibold text-foreground mb-1">
                    {selected.facility_name || 'Unknown Facility'}
                  </h3>
                  <p className="text-body-sm text-muted-foreground">{selected.district_name}</p>
                </div>

                {/* What is happening */}
                <section>
                  <h4 className="text-caption font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                    What is Happening
                  </h4>
                  <p className="text-body text-foreground/90 leading-relaxed">
                    {selected.what_is_happening || 'No analysis available.'}
                  </p>
                </section>

                {/* Root cause */}
                {selected.why_it_happening && (
                  <section>
                    <h4 className="text-caption font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                      Root Cause
                    </h4>
                    <p className="text-body text-foreground/90 leading-relaxed">
                      {selected.why_it_happening}
                    </p>
                  </section>
                )}

                {/* Recommended action */}
                {selected.recommended_action && (
                  <section className="rounded-lg bg-info/8 border border-info/20 px-4 py-3">
                    <h4 className="text-caption font-semibold text-info uppercase tracking-wider mb-1.5">
                      Recommended Action
                    </h4>
                    <p className="text-body text-foreground/90 leading-relaxed">
                      {selected.recommended_action}
                    </p>
                  </section>
                )}

                {/* Confidence + metadata */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="rounded-lg border border-border/60 p-3">
                    <span className="text-caption text-muted-foreground block mb-1">AI Confidence</span>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-1.5 rounded-full bg-secondary">
                        <div
                          className="h-full rounded-full bg-accent transition-all"
                          style={{ width: `${Math.round((selected.confidence_score || 0) * 100)}%` }}
                        />
                      </div>
                      <span className="text-body-sm font-mono font-semibold text-foreground">
                        {Math.round((selected.confidence_score || 0) * 100)}%
                      </span>
                    </div>
                  </div>
                  <div className="rounded-lg border border-border/60 p-3">
                    <span className="text-caption text-muted-foreground block mb-1">Source</span>
                    <div className="flex items-center gap-1.5">
                      {selected.llm_generated ? (
                        <Badge variant="accent" size="sm">AI Generated</Badge>
                      ) : (
                        <Badge variant="secondary" size="sm">Rule Based</Badge>
                      )}
                    </div>
                  </div>
                </div>

                {/* Timeline */}
                <section>
                  <h4 className="text-caption font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                    Timeline
                  </h4>
                  <div className="flex items-center gap-2 text-caption text-muted-foreground">
                    <Clock className="h-3 w-3" />
                    <span>Created {timeAgo(selected.created_at)}</span>
                    <ArrowRight className="h-3 w-3" />
                    <span>Active — no expiry</span>
                  </div>
                </section>
              </div>
            )}
          </ScrollArea>
        </Card>
      </div>
    </section>
  )
}
