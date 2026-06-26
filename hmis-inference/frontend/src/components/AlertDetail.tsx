import { cn } from '@/lib/utils'

function ConfidenceBar({ score }: { score: number }) {
  const pct = Math.round((score || 0) * 100)
  const color = pct >= 70 ? 'bg-success' : pct >= 40 ? 'bg-severity-medium' : 'bg-severity-critical'
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-body-sm font-medium text-muted-foreground">AI Confidence</span>
        <span className="text-body-sm font-semibold text-foreground font-mono">{pct}%</span>
     </div>
      <div className="h-1.5 rounded-full bg-secondary overflow-hidden">
        <div className={cn('h-full rounded-full transition-all duration-500 ease-out', color)} style={{ width: `${pct}%` }} />
     </div>
   </div>
  )
}

function RiskScore({ score }: { score: number }) {
  const color = score >= 0.7 ? 'text-severity-critical' : score >= 0.4 ? 'text-severity-medium' : 'text-success'
  const bg = score >= 0.7 ? 'bg-severity-critical/10' : score >= 0.4 ? 'bg-severity-medium/10' : 'bg-success/10'
  const label = score >= 0.7 ? 'Critical' : score >= 0.4 ? 'Elevated' : 'Normal'
  return (
    <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-secondary/50 border border-border/60">
      <div className={cn('w-9 h-9 rounded-md grid place-items-center text-body-sm font-bold font-mono shrink-0', bg, color)}>
        {Math.round((score || 0) * 100)}
     </div>
      <div className="min-w-0">
        <span className="text-caption text-muted-foreground block">Risk Score</span>
        <span className={cn('text-body-sm font-semibold', color)}>{label</span>
     </div>
   </div>
  )
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full px-8">
      <div className="w-12 h-12 rounded-xl bg-secondary grid place-items-center mb-4">
        <svg className="w-6 h-6 text-muted-foreground/40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
          <path d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
       </svg>
     </div>
      <h3 className="text-body-sm font-semibold text-foreground mb-1">Select an alert</h3>
      <p className="text-caption text-muted-foreground text-center max-w-[240px] leading-relaxed">
        Choose an alert from the feed to view the full investigation report, root cause analysis, and AI-recommended actions.
     </p>
   </div>
  )
}

// Shown when an alert is selected but the active filter excludes it.
// Replaces the alert body with a friendly "Clear filter" affordance so the
// user is not looking at a stale investigation.
function FilteredOutState({ alert, onClearFilter }: { alert: any; onClearFilter?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-8 text-center animate-fade-in">
      <div className="w-12 h-12 rounded-xl bg-secondary grid place-items-center mb-4">
        <svg className="w-6 h-6 text-muted-foreground/50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 4h18M6 4v16a2 2 0 002 2h8a2 2 0 002-2V4M10 11h4" />
       </svg>
     </div>
      <h3 className="text-body-sm font-semibold text-foreground mb-1">Alert filtered out</h3>
      <p className="text-caption text-muted-foreground mb-4 max-w-[280px] leading-relaxed">
        You selected{' '}
        <span className="font-semibold text-foreground/80">{alert.facility_name || 'this alert'</span>
        {alert.district_name && (
          <>
            {' '}in <span className="font-semibold text-foreground/80">{alert.district_name</span>
          </>
        )}
        , but the current filter hides it. Clear the filter to view the full investigation.
     </p>
      {onClearFilter && (
        <button
          type="button"
          onClick={onClearFilter}
          className="h-8 px-3 rounded-md bg-foreground text-background text-caption font-medium hover:opacity-90 transition-opacity cursor-pointer"
        >
          Clear filter
       </button>
      )}
   </div>
  )
}

function formatTimestamp(dateStr: string) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

interface AlertDetailProps {
  alert: any
  isFilteredOut?: boolean
  onClearFilter?: () => void
}

export function AlertDetail({ alert, isFilteredOut, onClearFilter }: AlertDetailProps) {
  if (!alert) {
    return (
      <div className="flex items-center justify-center h-full">
        <EmptyState />
     </div>
    )
  }

  if (isFilteredOut) {
    return <FilteredOutState alert={alert} onClearFilter={onClearFilter} />
  }

  const sevColor = alert.severity === 'HIGH' ? 'text-severity-critical bg-severity-critical/10'
    : alert.severity === 'MEDIUM' ? 'text-severity-medium bg-severity-medium/10'
    : 'text-success bg-success/10'

  return (
    <div className="h-full overflow-y-auto animate-fade-in">
      {/* Sticky header */}
      <div className="sticky top-0 z-10 bg-card/95 backdrop-blur-sm border-b border-border/60 px-5 py-3.5">
        <div className="flex items-center gap-2 mb-1">
          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded uppercase tracking-wider leading-none ${sevColor}`}>
            {alert.severity}
         </span>
          {alert.inference_type && (
            <span className="text-caption text-muted-foreground">{alert.inference_type</span>
          )}
          {alert.created_at && (
            <>
              <span className="text-border text-caption">·</span>
              <span className="text-caption text-muted-foreground">{formatTimestamp(alert.created_at)}</span>
            </>
          )}
       </div>
        <h2 className="text-heading-sm font-semibold text-foreground tracking-tight">
          {alert.facility_name || 'Unknown Facility'}
       </h2>
        <p className="text-caption text-muted-foreground mt-0.5">{alert.district_name</p>
     </div>

      {/* Content */}
      <div className="px-5 py-5 space-y-5">
        <section>
          <h3 className="text-body-sm font-semibold text-foreground mb-1.5">What is Happening</h3>
          <p className="text-body text-foreground/80 leading-relaxed">
            {alert.what_is_happening || 'No analysis available.'}
         </p>
       </section>

        {alert.why_it_happening && (
          <section>
            <h3 className="text-body-sm font-semibold text-foreground mb-1.5">Root Cause</h3>
            <p className="text-body text-foreground/80 leading-relaxed">{alert.why_it_happening</p>
         </section>
        )}

        {alert.recommended_action && (
          <section className="px-3 py-2.5 rounded-lg bg-info/8 border border-info/20">
            <h3 className="text-caption font-semibold text-info mb-1 uppercase tracking-wider">Recommended Action</h3>
            <p className="text-body text-foreground/80 leading-relaxed">{alert.recommended_action</p>
         </section>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-0.5">
          <RiskScore score={alert.confidence_score} />
          <ConfidenceBar score={alert.confidence_score} />
       </div>

        {alert.rule_flags && (Array.isArray(alert.rule_flags) ? alert.rule_flags.length > 0 : true) && (
          <section>
            <h3 className="text-body-sm font-semibold text-foreground mb-2">Triggered Rules</h3>
            <div className="flex flex-wrap gap-1.5">
              {(Array.isArray(alert.rule_flags) ? alert.rule_flags : [alert.rule_flags]).map((r: any, i: number) => (
                <span key={i} className="text-caption text-muted-foreground bg-secondary border border-border/60 px-2 py-0.5 rounded-md">
                  {typeof r === 'string' ? r : r?.rule_name || JSON.stringify(r)}
               </span>
              ))}
           </div>
         </section>
        )}
     </div>
   </div>
  )
}
