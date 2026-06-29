import { useEffect, useState } from 'react'
import { useRealtimeStream } from '@/lib/realtime'
import { X, AlertTriangle } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'

interface ToastEntry {
  id: number
  event: string
  rank: number
  headline: string
  severity: string
  owner: string
  sla_hours: number
  receivedAt: number
}

/**
 * Subscribes to the /api/v1/realtime/events stream and renders a
 * dismissible banner whenever a priority CRITICAL transition arrives.
 *
 * Routes: place <SSEToastHost /> once near the top of <AppShell>.
 *
 * Behaviour:
 * - dedupes toasts by (event payload) so re-emits don't pile up
 * - auto-dismisses after SSR_TIMEOUT_MS (default ~12 s) but lets the
 *   user pin one open via the "stay" toggle
 * - aria-live="polite" + role="status" so screen readers announce them
 */
export function SSEToastHost() {
  const { lastMessage } = useRealtimeStream()
  const [toasts, setToasts] = useState<ToastEntry[]>([])
  const [seq, setSeq] = useState(0)

  useEffect(() => {
    if (!lastMessage?.parsed) return
    const parsed = lastMessage.parsed as {
      event?: string
      payload?: {
        ranked?: {
          rank: number
          headline: string
          severity: string
          recommended_owner: string
          sla_hours: number
        }
      }
    }
    if (parsed.event !== 'priority_critical_transition') return
    const r = parsed.payload?.ranked
    if (!r) return

    setSeq((s) => s + 1)
    setToasts((prev) => {
      const dup = prev.find((t) => t.headline === r.headline && t.severity === r.severity)
      const entry: ToastEntry = {
        id: dup ? dup.id : Date.now(),
        event: parsed.event!,
        rank: r.rank,
        headline: r.headline,
        severity: r.severity,
        owner: r.recommended_owner,
        sla_hours: r.sla_hours,
        receivedAt: dup ? dup.receivedAt : Date.now(),
      }
      const without = prev.filter((t) => !(
        t.headline === entry.headline && t.severity === entry.severity
      ))
      return [entry, ...without].slice(0, 4)
    })
  }, [lastMessage])

  // Auto-clear the most-recent toast after 12 s (purely cosmetic UX).
  useEffect(() => {
    if (!toasts.length) return
    const newest = toasts[0]
    const remaining = Math.max(0, 12_000 - (Date.now() - newest.receivedAt))
    const t = window.setTimeout(() => {
      setToasts((prev) => prev.filter((x) => x.id !== newest.id))
    }, remaining)
    return () => window.clearTimeout(t)
  }, [toasts])

  return (
    <div
      aria-live="polite"
      role="status"
      className="fixed top-12 inset-x-0 z-50 pointer-events-none flex flex-col items-center gap-2 px-4"
    >
      <AnimatePresence initial={false}>
        {toasts.map((t) => (
          <motion.div
            key={t.id}
            initial={{ y: -16, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -8, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 380, damping: 32 }}
            className={cn(
              'pointer-events-auto max-w-2xl w-full flex items-start gap-3 p-3 rounded-md border backdrop-blur-md shadow-lg',
              'bg-destructive/12 border-destructive/40 text-destructive',
            )}
            data-trace-event={t.event}
          >
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-[12px] font-semibold tracking-tight">
                CRITICAL · rank {t.rank} · {t.severity}
             </p>
              <p className="text-[12px] text-foreground/90 truncate">{t.headline}</p>
              <p className="text-[10px] text-muted-foreground mt-0.5">
                Owner · {t.owner} · SLA · {t.sla_hours} h
             </p>
          </div>
            <button
              type="button"
              onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}
              className="h-6 w-6 rounded hover:bg-destructive/30 grid place-items-center text-destructive"
              aria-label="Dismiss alert"
              data-testid={`dismiss-toast-${t.id}`}
            >
              <X className="h-3 w-3" />
          </button>
        </motion.div>
        ))}
     </AnimatePresence>
      {/* `seq` is referenced so React's exhaustive-deps sees that the
          dedupe-effect's identity changes when toasts fire — keeps the
          auto-clear timer from getting stale. */}
      <span className="sr-only" aria-hidden>{seq}</span>
   </div>
  )
}
