import { useState, useEffect } from 'react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Card } from '@/components/ui/card'
import { OutbreakRiskWidget } from '@/components/dashboard/OutbreakRiskWidget'
import { HospitalPressureWidget } from '@/components/dashboard/HospitalPressureWidget'
import { PriorityRankWidget } from '@/components/dashboard/PriorityRankWidget'
import { PolicyMemoPanel } from '@/components/dashboard/PolicyMemoPanel'
import { useRealtimeStream } from '@/lib/realtime'

export default function HealthCommissionerDashboard() {
  const [districtId, setDistrictId] = useState<string | null>(null)
  const [diseaseName, setDiseaseName] = useState<string | null>(null)
  const { status, lastMessage } = useRealtimeStream()

  // When the server pushes a cache_warmed event or a CRITICAL
  // transition, trigger a global refetch counter so children
  // can re-evaluate stale TanStack Query snapshots on demand.
  const [, force] = useState(0)
  useEffect(() => {
    if (!lastMessage?.parsed) return
    const evt = (lastMessage.parsed as { event?: string }).event
    if (evt === 'cache_warmed' || evt === 'priority_critical_transition') {
      force((n) => n + 1)
    }
  }, [lastMessage])

  return (
    <section className="animate-fade-in space-y-6">
      <PageHeader
        eyebrow="Daily Briefing"
        title="Health Commissioner Dashboard"
        description="Today's view of outbreaks, hospital pressure, and priority actions. Updates every 15 minutes."
        actions={
          <span
            className={
              'text-[10px] tracking-widest px-2 py-0.5 rounded border ' +
              (status === 'open'
                ? 'border-success/30 bg-success/10 text-success'
                : status === 'closed'
                  ? 'border-destructive/30 bg-destructive/10 text-destructive'
                  : 'border-border/60 bg-card text-muted-foreground')
            }
          >
            {status === 'open' ? 'live' : status === 'closed' ? 'disconnected' : 'connecting…'}
      </span>
        }
      />

      <Card className="p-4 border-border/80 bg-card/60 backdrop-blur-md flex flex-wrap items-center gap-3">
        <label className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          Focus
      </label>
        <select
          value={districtId ?? ''}
          onChange={(e) => setDistrictId(e.target.value || null)}
          className="h-8 px-2 rounded border border-border/80 bg-card text-[12px] text-foreground outline-none focus:border-accent"
        >
          <option value="">All Gujarat</option>
          <option value="b663e6d9-bcb9-488d-9625-12d882bf06a0">Ahmedabad</option>
          <option value="cadc66f3-2937-4015-84d8-4b51981e696e">Surat</option>
          <option value="123287fb-a1db-443f-9cdf-ee5fbb8e8e99">Vadodara</option>
          <option value="83bcb628-4b2f-465d-b419-c5262320055b">Rajkot</option>
          <option value="3515b643-184f-48aa-ba7d-0997b7ae2d53">Bhavnagar</option>
      </select>
        <select
          value={diseaseName ?? ''}
          onChange={(e) => setDiseaseName(e.target.value || null)}
          className="h-8 px-2 rounded border border-border/80 bg-card text-[12px] text-foreground outline-none focus:border-accent"
        >
          <option value="">All diseases</option>
          <option value="Dengue">Dengue</option>
          <option value="Malaria">Malaria</option>
          <option value="Chikungunya">Chikungunya</option>
          <option value="Diarrheal">Diarrheal</option>
      </select>
        <span className="ml-auto text-[10px] text-muted-foreground">
          Updates every 15 minutes
      </span>
    </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <OutbreakRiskWidget districtId={districtId} diseaseName={diseaseName} />
        <HospitalPressureWidget districtId={districtId} />
        <PriorityRankWidget districtId={districtId} />
        <div className="rounded-lg border border-dashed border-border/60 p-4 text-[12px] text-muted-foreground space-y-2 bg-card/40">
          <h3 className="text-subheading font-semibold tracking-tight text-foreground">
            Daily Brief
        </h3>
          <p>
            The Policy Memo aggregator reads WS1 + WS2 + WS3 outputs and
            acts as the Commissioner&apos;s single-page brief. Open the
            collapsible panel below — actions are pre-cited against the
            ranked list above.
        </p>
      </div>
    </div>

      <PolicyMemoPanel districtId={districtId} />
  </section>
  )
}
