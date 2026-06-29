import { useQuery } from '@tanstack/react-query'

import client from '@/api/client'
import { WidgetShell } from './WidgetShell'
import type { PriorityRankEnvelope, RankedAction } from '@/lib/inference-types'
import { cn } from '@/lib/utils'

interface PriorityRankWidgetProps {
  districtId?: string | null
}

const SEV_PILL: Record<RankedAction['severity'], string> = {
  LOW:      'bg-secondary text-muted-foreground',
  MEDIUM:   'bg-warning/15 text-warning',
  HIGH:     'bg-severity-high/15 text-severity-high',
  CRITICAL: 'bg-destructive/15 text-destructive',
}

export function PriorityRankWidget({ districtId }: PriorityRankWidgetProps) {
  const query = useQuery<PriorityRankEnvelope>({
    queryKey: ['inference', 'priority-rank', districtId],
    queryFn: async ({ signal }) => {
      const params: Record<string, string> = {}
      if (districtId) params.district_id = districtId
      const res = await client.get('/api/v1/inference/priority-rank', { params, signal })
      return res.data as PriorityRankEnvelope
    },
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  })

  const ranked: RankedAction[] = (query.data?.data?.ranked ?? []) as RankedAction[]

  return (
    <WidgetShell
      title="Priority Actions Today"
      subtitle="Top 5 ranked policy items · owner + SLA"
      severity={query.data?.severity ?? null}
      confidence={query.data?.confidence ?? null}
      generatedAt={query.data?.generated_at ?? null}
      isLoading={query.isLoading}
      isError={query.isError}
      onRefresh={() => query.refetch()}
    >
      {ranked.length === 0 ? (
        <p className="text-[12px] text-muted-foreground">
          No priority items — operations are within normal range.
       </p>
      ) : (
        <ol className="space-y-2.5">
          {ranked.map((action) => (
            <li
              key={action.rank}
              className="border-b border-border/30 pb-2 last:border-b-0 last:pb-0"
            >
              <div className="flex items-start gap-3">
                <span className="h-6 w-6 rounded-full bg-accent text-accent-foreground grid place-items-center font-semibold text-[12px] shrink-0">
                  {action.rank}
               </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span
                      className={cn(
                        'text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded font-semibold',
                        SEV_PILL[action.severity],
                      )}
                    >
                      {action.severity}
                   </span>
                    <span className="text-[10px] text-muted-foreground">
                      severity score {action.severity_score.toFixed(2)}
                   </span>
                 </div>
                  <p className="text-[12px] text-foreground leading-snug mt-1">
                    {action.headline}
                 </p>
                  <p className="text-[11px] text-muted-foreground leading-snug mt-0.5 line-clamp-2">
                    {action.recommended_step}
                 </p>
                  <div className="flex items-center gap-2 mt-1.5 text-[10px] text-muted-foreground">
                    <span className="px-1.5 py-0.5 rounded bg-secondary/60 border border-border/40">
                      Owner · {action.recommended_owner}
                   </span>
                    <span className="px-1.5 py-0.5 rounded bg-secondary/60 border border-border/40">
                      SLA · {action.sla_hours} h
                   </span>
                 </div>
               </div>
             </div>
           </li>
          ))}
       </ol>
      )}
   </WidgetShell>
  )
}
