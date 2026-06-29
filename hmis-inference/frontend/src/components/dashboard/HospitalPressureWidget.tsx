import { useQuery } from '@tanstack/react-query'
import { TrendingUp, TrendingDown, Minus, ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'

import client from '@/api/client'
import { WidgetShell } from './WidgetShell'
import type { HospitalPressureEnvelope, PressureSignal } from '@/lib/inference-types'
import { cn } from '@/lib/utils'

interface HospitalPressureWidgetProps {
  districtId?: string | null
  facilityId?: string | null
}

const TIER_DOT: Record<PressureSignal['tier'], string> = {
  Normal:   'bg-success',
  Strained: 'bg-warning',
  Critical: 'bg-destructive',
}

function trendIcon(trend: PressureSignal['trend_48h']) {
  const c = 'h-3 w-3 shrink-0'
  if (trend === 'rising') return <TrendingUp className={cn(c, 'text-destructive')} />
  if (trend === 'easing') return <TrendingDown className={cn(c, 'text-success')} />
  return <Minus className={cn(c, 'text-muted-foreground')} />
}

const PAGE_SIZE = 25

export function HospitalPressureWidget({ districtId, facilityId }: HospitalPressureWidgetProps) {
  const [expanded, setExpanded] = useState(false)
  const query = useQuery<HospitalPressureEnvelope>({
    queryKey: ['inference', 'hospital-pressure', districtId, facilityId, expanded ? 'all' : 'top'],
    queryFn: async ({ signal }) => {
      const params: Record<string, string | number> = {
        limit: expanded ? 500 : PAGE_SIZE,
      }
      if (districtId) params.district_id = districtId
      if (facilityId) params.facility_id = facilityId
      const res = await client.get('/api/v1/inference/hospital-pressure', { params, signal })
      return res.data as HospitalPressureEnvelope
    },
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  })

  const signals: PressureSignal[] = (query.data?.data?.signals ?? []) as PressureSignal[]
  const visible = expanded ? signals : signals.slice(0, 6)
  const total = signals.length

  return (
    <WidgetShell
      title="Hospital Pressure"
      subtitle="Per facility · 48-hour trend projection"
      severity={query.data?.severity ?? null}
      confidence={query.data?.confidence ?? null}
      generatedAt={query.data?.generated_at ?? null}
      isLoading={query.isLoading}
      isError={query.isError}
      onRefresh={() => query.refetch()}
      action={
        total > PAGE_SIZE ? (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="h-6 px-2 text-[10px] uppercase tracking-wider rounded border border-border/60 text-muted-foreground hover:text-foreground hover:bg-secondary/60 inline-flex items-center gap-1"
          >
            {expanded ? (
              <>
                <ChevronDown className="h-3 w-3 rotate-180" />
                top only
              </>
            ) : (
              <>
                <ChevronRight className="h-3 w-3" />
                all {total}
              </>
            )}
         </button>
        ) : null
      }
    >
      {visible.length === 0 ? (
        <p className="text-[12px] text-muted-foreground">
          No facility pressure signals in scope.
       </p>
      ) : (
        <ul className="space-y-2.5">
          {visible.map((s) => (
            <li
              key={s.facility_id}
              className="flex items-start gap-2 text-[12px] border-b border-border/30 pb-2 last:border-b-0"
            >
              <span className={cn('mt-1 h-2 w-2 rounded-full shrink-0', TIER_DOT[s.tier])} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-foreground truncate">{s.facility_name}</span>
                  <span className="text-[10px] uppercase tracking-wider font-semibold text-foreground/80 shrink-0">
                    {s.tier}
                 </span>
               </div>
                <div className="flex items-center gap-3 text-muted-foreground mt-0.5 flex-wrap">
                  <span>ICU {s.icu_occupancy_pct.toFixed(0)}%</span>
                  <span>Bed {s.bed_occupancy_pct.toFixed(0)}%</span>
                  <span className="inline-flex items-center gap-1">
                    {trendIcon(s.trend_48h)}
                    48&nbsp;h&nbsp;{s.trend_48h}
                 </span>
               </div>
                {s.icu_pred_48h != null ? (
                  <p className="text-[10px] text-muted-foreground/70 mt-0.5">
                    Projection · ICU → {s.icu_pred_48h.toFixed(0)}% · bed →{' '}
                    {s.bed_pred_48h?.toFixed(0) ?? '—'}%
                 </p>
                ) : null}
             </div>
           </li>
          ))}
       </ul>
      )}
   </WidgetShell>
  )
}
