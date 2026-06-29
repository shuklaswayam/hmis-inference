import { ReactNode } from 'react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Clock, AlertTriangle, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Severity } from '@/lib/inference-types'

interface WidgetShellProps {
  title: string
  subtitle?: string
  severity?: Severity | null
  confidence?: number | null
  generatedAt?: string | null
  isLoading?: boolean
  isError?: boolean
  onRefresh?: () => void
  children?: ReactNode
  action?: ReactNode
}

const SEV_STYLES: Record<Severity, string> = {
  LOW:      'bg-secondary text-muted-foreground border-border',
  MEDIUM:   'bg-warning/10 text-warning border-warning/30',
  HIGH:     'bg-severity-high/15 text-severity-high border-severity-high/40',
  CRITICAL: 'bg-destructive/15 text-destructive border-destructive/40',
}

function freshnessLabel(generatedAt?: string | null) {
  if (!generatedAt) return 'no data yet'
  const ageMin = Math.max(0, Math.floor((Date.now() - new Date(generatedAt).getTime()) / 60000))
  if (ageMin < 1) return 'just now'
  if (ageMin < 60) return `${ageMin} min ago`
  return `${Math.floor(ageMin / 60)} h ago`
}

export function WidgetShell({
  title,
  subtitle,
  severity,
  confidence,
  generatedAt,
  isLoading,
  isError,
  onRefresh,
  children,
  action,
}: WidgetShellProps) {
  return (
    <Card className="overflow-hidden border-border/80 bg-card/60 backdrop-blur-md">
      <div className="flex items-start justify-between gap-2 px-4 pt-3 pb-2 border-b border-border/40">
        <div className="min-w-0">
          <h3 className="text-subheading font-semibold tracking-tight text-foreground truncate">
            {title}
         </h3>
          {subtitle ? (
            <p className="text-caption text-muted-foreground truncate">{subtitle}</p>
          ) : null}
       </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {severity ? (
            <span
              className={cn(
                'text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border',
                SEV_STYLES[severity],
              )}
            >
              {severity}
           </span>
          ) : null}
          {typeof confidence === 'number' ? (
            <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border border-accent/30 bg-accent/10 text-accent">
              conf {Math.round(confidence * 100)}%
           </span>
          ) : null}
          {action}
          {onRefresh ? (
            <button
              type="button"
              onClick={onRefresh}
              className="h-6 w-6 rounded border border-border/60 text-muted-foreground hover:text-foreground hover:bg-secondary/60 grid place-items-center transition-colors"
              aria-label="Refresh widget"
            >
              <RefreshCw className="h-3 w-3" />
           </button>
          ) : null}
       </div>
     </div>

      <div className="px-4 py-2 border-b border-border/30 flex items-center gap-1.5 text-[10px] text-muted-foreground">
        <Clock className="h-3 w-3" />
        <span>Last updated {freshnessLabel(generatedAt)}</span>
     </div>

      <div className="px-4 py-3">
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-3/4 opacity-30" />
            <Skeleton className="h-4 w-2/3 opacity-30" />
            <Skeleton className="h-4 w-1/2 opacity-30" />
         </div>
        ) : isError ? (
          <div className="flex items-center gap-2 text-[12px] text-destructive">
            <AlertTriangle className="h-4 w-4" />
            Failed to load inference output. Backend may be down.
         </div>
        ) : (
          children
        )}
     </div>
   </Card>
  )
}
