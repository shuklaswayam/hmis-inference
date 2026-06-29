import { useQuery } from '@tanstack/react-query'

import client from '@/api/client'
import { WidgetShell } from './WidgetShell'
import type { OutbreakRiskEnvelope, OutbreakSignal } from '@/lib/inference-types'
import { cn } from '@/lib/utils'

interface OutbreakRiskWidgetProps {
  districtId?: string | null
  diseaseName?: string | null
}

const TIER_STYLES: Record<OutbreakSignal['tier'], string> = {
  Low:      'border-l-blue-400 bg-blue-400/5',
  Medium:   'border-l-amber-400 bg-amber-400/5',
  High:     'border-l-orange-500 bg-orange-500/5',
  Critical: 'border-l-destructive bg-destructive/5',
}

export function OutbreakRiskWidget({ districtId, diseaseName }: OutbreakRiskWidgetProps) {
  const query = useQuery<OutbreakRiskEnvelope>({
    queryKey: ['inference', 'outbreak-risk', districtId, diseaseName],
    queryFn: async ({ signal }) => {
      const params: Record<string, string> = {}
      if (districtId) params.district_id = districtId
      if (diseaseName) params.disease_name = diseaseName
      const res = await client.get('/api/v1/inference/outbreak-risk', { params, signal })
      return res.data as OutbreakRiskEnvelope
    },
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  })

  const signals: OutbreakSignal[] = (query.data?.data?.signals ?? []) as OutbreakSignal[]
  // Show top 5 — sort so Critical/High are first (defensive; backend
  // already sorts, this protects against older cached payloads).
  const visible = [...signals].sort((a, b) =>
    ['Critical', 'High', 'Medium', 'Low'].indexOf(a.tier) -
    ['Critical', 'High', 'Medium', 'Low'].indexOf(b.tier),
  ).slice(0, 5)

  return (
    <WidgetShell
      title="Outbreak Risk"
      subtitle="Per ward × disease, 14-day baseline vs. recent"
      severity={query.data?.severity ?? null}
      confidence={query.data?.confidence ?? null}
      generatedAt={query.data?.generated_at ?? null}
      isLoading={query.isLoading}
      isError={query.isError}
      onRefresh={() => query.refetch()}
    >
      {visible.length === 0 ? (
        <p className="text-[12px] text-muted-foreground">
          No active outbreak signals at this scope.
       </p>
      ) : (
        <ul className="space-y-2">
          {visible.map((s, i) => (
            <li
              key={`${s.district_id}-${s.disease_name}-${i}`}
              className={cn(
                'border-l-2 px-3 py-2 rounded-r-md text-[12px]',
                TIER_STYLES[s.tier],
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-foreground truncate">
                  {s.disease_name}{' '}
                  <span className="text-muted-foreground">· {s.district_name}</span>
               </span>
                <span className="text-[10px] uppercase tracking-wider font-semibold text-foreground/80 shrink-0">
                  {s.tier}
               </span>
             </div>
              <p className="text-muted-foreground mt-1 line-clamp-2">{s.recommended_action}</p>
              <p className="text-[10px] text-muted-foreground/70 mt-0.5">
                {Math.round(s.confidence * 100)}% confidence ·{' '}
                {s.cases_last_14d} cases · {s.baseline_ratio.toFixed(1)}× baseline
             </p>
           </li>
          ))}
       </ul>
      )}
   </WidgetShell>
  )
}
