import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, Copy, Sparkles, RotateCcw } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

import client from '@/api/client'
import type { PolicyMemoEnvelope } from '@/lib/inference-types'
import { cn } from '@/lib/utils'

interface PolicyMemoPanelProps {
  districtId?: string | null
  defaultOpen?: boolean
}

export function PolicyMemoPanel({ districtId, defaultOpen = false }: PolicyMemoPanelProps) {
  const [open, setOpen] = useState<boolean>(defaultOpen)
  const [copied, setCopied] = useState<boolean>(false)

  const query = useQuery<PolicyMemoEnvelope>({
    queryKey: ['inference', 'policy-memo', districtId],
    queryFn: async ({ signal }) => {
      const params: Record<string, string> = {}
      if (districtId) params.district_id = districtId
      const res = await client.get('/api/v1/inference/policy-memo', { params, signal })
      return res.data as PolicyMemoEnvelope
    },
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
    enabled: open, // laziness — don't fetch until the user opens the panel
  })

  const memo = query.data?.data
  const llmGenerated = memo?.llm_generated ?? false

  const copyMarkdown = async () => {
    if (!memo) return
    const text = `# ${memo.headline}\n\n${memo.body_md}\n\n## Actions\n${
      memo.recommended_actions
        .map((a) => `- ${a.action}  ·  Owner: ${a.owner}  ·  SLA: ${a.sla_hours}h`)
        .join('\n')
    }`
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      // clipboard denied; ignore silently
    }
  }

  return (
    <section className="rounded-lg border border-border/80 bg-card/60 backdrop-blur-md overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 hover:bg-secondary/30 transition-colors text-left"
        aria-expanded={open}
      >
        <div className="flex items-center gap-2 min-w-0">
          <Sparkles className="h-4 w-4 text-accent shrink-0" />
          <h2 className="text-subheading font-semibold tracking-tight truncate">
            Policy Memo — Daily Brief
         </h2>
          {memo ? (
            <span className="text-caption text-muted-foreground truncate">
              {memo.headline}
           </span>
          ) : null}
          {llmGenerated ? (
            <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border border-accent/30 bg-accent/10 text-accent">
              AI-drafted
           </span>
          ) : null}
       </div>
        <div className="flex items-center gap-2 shrink-0">
          {open ? (
            <>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  query.refetch()
                }}
                className="h-6 w-6 rounded border border-border/60 text-muted-foreground hover:text-foreground hover:bg-secondary/60 grid place-items-center"
                aria-label="Regenerate memo"
              >
                <RotateCcw className="h-3 w-3" />
             </button>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  void copyMarkdown()
                }}
                className={cn(
                  'h-6 px-2 text-[10px] uppercase tracking-wider rounded border transition-colors',
                  copied
                    ? 'border-success/40 bg-success/10 text-success'
                    : 'border-border/60 text-muted-foreground hover:text-foreground hover:bg-secondary/60',
                )}
              >
                {copied ? 'Copied' : <Copy className="h-3 w-3" />}
             </button>
            </>
          ) : null}
          <ChevronDown
            className={cn(
              'h-4 w-4 text-muted-foreground transition-transform',
              open && 'rotate-180',
            )}
          />
       </div>
     </button>

      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            key="memo-body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 320, damping: 32 }}
            className="overflow-hidden border-t border-border/40"
          >
            <div className="px-5 py-4 space-y-3 text-[13px]">
              {query.isLoading && !memo ? (
                <div className="space-y-2">
                  <div className="h-4 w-2/3 rounded bg-secondary/60 animate-pulse" />
                  <div className="h-4 w-1/2 rounded bg-secondary/60 animate-pulse" />
                  <div className="h-4 w-3/4 rounded bg-secondary/60 animate-pulse" />
               </div>
              ) : null}
              {query.isError ? (
                <p className="text-destructive text-[12px]">
                  Memo backend is unavailable. The router will fall back to a
                  structured template in production.
               </p>
              ) : null}

              {memo ? (
                <>
                  <h3 className="text-heading-sm font-semibold tracking-tight text-foreground">
                    {memo.headline}
                 </h3>
                  <article className="prose prose-invert max-w-none text-[13px] leading-relaxed text-foreground/85 whitespace-pre-wrap">
                    {memo.body_md}
                 </article>
                  {memo.recommended_actions?.length ? (
                    <div>
                      <h4 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                        Recommended Actions
                     </h4>
                      <ul className="space-y-1.5">
                        {memo.recommended_actions.map((a, i) => (
                          <li
                            key={i}
                            className="border-l-2 border-accent/60 pl-3 py-1 rounded-r-md bg-accent/5"
                          >
                            <p className="text-[12px] text-foreground">{a.action}</p>
                            <p className="text-[10px] text-muted-foreground mt-0.5">
                              Owner · {a.owner}  ·  Complete within {a.sla_hours} hours
                           </p>
                         </li>
                        ))}
                     </ul>
                   </div>
                  ) : null}
                  <p className="text-[10px] text-muted-foreground/70 pt-2 border-t border-border/30">
                    Generated {memo.llm_generated ? 'via LLM' : 'from a structured fallback template'} ·{' '}
                    refresh every 15 min · last update{' '}
                    {query.data?.generated_at
                      ? new Date(query.data.generated_at).toLocaleString()
                      : 'n/a'}
                 </p>
                </>
              ) : null}
           </div>
         </motion.div>
        ) : null}
     </AnimatePresence>
   </section>
  )
}
