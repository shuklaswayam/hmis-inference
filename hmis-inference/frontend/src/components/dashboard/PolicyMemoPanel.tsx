import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Copy, Sparkles, RotateCcw, ExternalLink, ListChecks } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

import client from '@/api/client'
import type { PolicyMemoEnvelope, MemoAction } from '@/lib/inference-types'
import { cn } from '@/lib/utils'

interface PolicyMemoPanelProps {
  districtId?: string | null
  defaultOpen?: boolean
}

// Severity colour class so the Commissioner can scan severity at a glance.
const SEVERITY_STYLE: Record<string, string> = {
  CRITICAL: 'border-red-500/60 bg-red-500/10 text-red-300',
  HIGH:     'border-orange-500/60 bg-orange-500/10 text-orange-300',
  MEDIUM:   'border-amber-500/60 bg-amber-500/10 text-amber-300',
  LOW:      'border-slate-500/60 bg-slate-500/10 text-slate-300',
}
const SEVERITY_ORDER: Record<string, number> = {
  CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3,
}

export function PolicyMemoPanel({ districtId, defaultOpen = false }: PolicyMemoPanelProps) {
  const [open, setOpen] = useState<boolean>(defaultOpen)
  const [copied, setCopied] = useState<boolean>(false)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

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
    enabled: open,
  })

  const memo = query.data?.data
  const llmGenerated = memo?.llm_generated ?? false

  const actions = useMemo<MemoAction[]>(() => {
    const raw = memo?.recommended_actions ?? []
    return [...raw].sort((a, b) => {
      const sa = SEVERITY_ORDER[(a.severity || 'MEDIUM').toUpperCase()] ?? 2
      const sb = SEVERITY_ORDER[(b.severity || 'MEDIUM').toUpperCase()] ?? 2
      return sa - sb
    })
  }, [memo])

  const toggle = (i: number) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })
  }

  const copyMarkdown = async () => {
    if (!memo) return
    const lines: string[] = []
    lines.push(`# ${memo.headline}`)
    lines.push('')
    lines.push(memo.body_md)
    lines.push('')
    lines.push('## Actions')
    for (const a of actions) {
      const sev = a.severity ? ` [${a.severity}]` : ''
      lines.push(`- ${a.action}${sev} · Owner: ${a.owner} · SLA: ${a.sla_hours}h`)
      if (a.description) lines.push(`    ${a.description}`)
      if (a.rationale) lines.push(`    Rationale: ${a.rationale}`)
      if (a.next_steps && a.next_steps.length) {
        lines.push('    Steps:')
        for (const s of a.next_steps) lines.push(`      - ${s}`)
      }
    }
    try {
      await navigator.clipboard.writeText(lines.join('\n'))
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      // clipboard denied
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
            Policy Memo &mdash; Daily Brief
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
                onClick={(e) => { e.stopPropagation(); query.refetch() }}
                className="h-6 w-6 rounded border border-border/60 text-muted-foreground hover:text-foreground hover:bg-secondary/60 grid place-items-center"
                aria-label="Regenerate memo"
              >
                <RotateCcw className="h-3 w-3" />
            </button>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); void copyMarkdown() }}
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
            className={cn('h-4 w-4 text-muted-foreground transition-transform', open && 'rotate-180')}
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
            <div className="px-5 py-4 space-y-4 text-[13px]">
              {query.isLoading && !memo ? (
                <div className="space-y-2">
                  <div className="h-4 w-2/3 rounded bg-secondary/60 animate-pulse" />
                  <div className="h-4 w-1/2 rounded bg-secondary/60 animate-pulse" />
                  <div className="h-4 w-3/4 rounded bg-secondary/60 animate-pulse" />
              </div>
              ) : null}
              {query.isError ? (
                <p className="text-destructive text-[12px]">
                  Memo backend is unavailable. The router will fall back to a structured template in production.
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

                  {actions.length ? (
                    <div>
                      <h4 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
                        <ListChecks className="h-3 w-3" />
                        Recommended Actions ({actions.length})
                    </h4>
                      <ul className="space-y-2">
                        {actions.map((a, i) => {
                          const sev = (a.severity || 'MEDIUM').toUpperCase()
                          const sevCls = SEVERITY_STYLE[sev] ?? SEVERITY_STYLE.MEDIUM
                          const isOpen = expanded.has(i)
                          return (
                            <li
                              key={i}
                              className="border border-border/40 rounded-md bg-card/40 overflow-hidden"
                            >
                              <button
                                type="button"
                                onClick={() => toggle(i)}
                                aria-expanded={isOpen}
                                className="w-full flex items-start gap-2 px-3 py-2 text-left hover:bg-secondary/30 transition-colors"
                              >
                                {isOpen ? (
                                  <ChevronDown className="h-3.5 w-3.5 mt-0.5 text-muted-foreground shrink-0" />
                                ) : (
                                  <ChevronRight className="h-3.5 w-3.5 mt-0.5 text-muted-foreground shrink-0" />
                                )}
                                <div className="min-w-0 flex-1">
                                  <p className="text-[12.5px] text-foreground font-medium leading-snug">
                                    {a.action}
                                </p>
                                  <p className="text-[10.5px] text-muted-foreground mt-1 flex items-center gap-2 flex-wrap">
                                    <span className={cn(
                                      'inline-block px-1.5 py-0.5 rounded border text-[9px] uppercase tracking-wider font-semibold',
                                      sevCls,
                                    )}>
                                      {sev}
                                  </span>
                                    <span>Owner &middot; {a.owner || 'Unassigned'}</span>
                                    <span>&middot; Complete within {a.sla_hours}h</span>
                                </p>
                              </div>
                            </button>

                              <AnimatePresence initial={false}>
                                {isOpen ? (
                                  <motion.div
                                    key="detail"
                                    initial={{ height: 0, opacity: 0 }}
                                    animate={{ height: 'auto', opacity: 1 }}
                                    exit={{ height: 0, opacity: 0 }}
                                    transition={{ duration: 0.18 }}
                                    className="overflow-hidden border-t border-border/30"
                                  >
                                    <div className="px-3 py-3 space-y-3 text-[12px] text-foreground/90">
                                      <div>
                                        <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">
                                          What is happening
                                       </p>
                                        <p className="leading-relaxed">{a.description || "No description was provided by the generator — refer to evidence refs and next steps below."}</p>
                                     </div>

                                      <div>
                                        <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">
                                          Why this matters &mdash; Evidence
                                       </p>
                                        <p className="leading-relaxed text-foreground/85">{a.rationale || "No rationale was provided — see evidence refs for the signals driving this action."}</p>
                                     </div>

                                      <div>
                                        <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">
                                          Source references
                                       </p>
                                        {a.evidence_refs && a.evidence_refs.length ? (
                                          <div className="flex flex-wrap gap-1.5">
                                            {a.evidence_refs.map((ref, ri) => (
                                              <span
                                                key={ri}
                                                className="inline-flex items-center gap-1 text-[10.5px] px-2 py-0.5 rounded border border-border/60 bg-secondary/40 text-foreground/80"
                                              >
                                                <ExternalLink className="h-2.5 w-2.5" />
                                                {ref}
                                            </span>
                                            ))}
                                         </div>
                                        ) : (
                                          <p className="leading-relaxed text-foreground/70 italic text-[11px]">
                                            No source references were attached to this action.
                                         </p>
                                        )}
                                     </div>

                                      <div>
                                        <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">
                                          Next steps for the owner
                                       </p>
                                        {a.next_steps && a.next_steps.length ? (
                                          <ol className="space-y-1 list-decimal list-inside marker:text-muted-foreground marker:text-[10px]">
                                            {a.next_steps.map((step, si) => (
                                              <li key={si} className="leading-relaxed pl-1">{step}</li>
                                            ))}
                                         </ol>
                                        ) : (
                                          <p className="leading-relaxed text-foreground/70 italic text-[11px]">
                                            No concrete next steps were provided.
                                         </p>
                                        )}
                                     </div>
                                 </div>
                                </motion.div>
                                ) : null}
                            </AnimatePresence>
                          </li>
                          )
                        })}
                    </ul>
                  </div>
                  ) : null}

                  <p className="text-[10px] text-muted-foreground/70 pt-2 border-t border-border/30">
                    Generated {llmGenerated ? 'via LLM' : 'from a structured fallback template'} &middot;
                    refresh every 15 min &middot; last update{' '}
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
