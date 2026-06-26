import { useState } from 'react'
import { cn } from '@/lib/utils'

const SEVERITY: Record<string, { color: string; bg: string; border: string; label: string }> = {
  HIGH: { color: 'text-severity-critical', bg: 'bg-severity-critical/10', border: 'border-severity-critical/30', label: 'Critical' },
  MEDIUM: { color: 'text-severity-medium', bg: 'bg-severity-medium/10', border: 'border-severity-medium/30', label: 'Warning' },
  LOW: { color: 'text-severity-low', bg: 'bg-severity-low/10', border: 'border-severity-low/30', label: 'Low' },
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

interface AlertCardProps {
  alert: any
  isSelected: boolean
  onSelect: (alert: any) => void
}

export function AlertCard({ alert, isSelected, onSelect }: AlertCardProps) {
  const [expanded, setExpanded] = useState(false)
  const sev = SEVERITY[alert.severity] || SEVERITY.LOW

  return (
    <div
      className={cn(
        'rounded-lg border bg-card hover:shadow-soft-sm transition-all duration-150 cursor-pointer',
        isSelected
          ? `border-current ${sev.color} ${sev.bg}`
          : 'border-border/60 hover:border-border',
      )}
      onClick={() => { onSelect?.(alert); setExpanded(!expanded) }}
    >
      <div className="px-3 py-2.5">
        {/* Top row */}
        <div className="flex items-start justify-between gap-2 mb-1.5">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-8 h-8 rounded-md bg-secondary grid place-items-center shrink-0 text-caption font-semibold text-muted-foreground">
              {(alert.facility_name || 'F')[0]}
            </div>
            <div className="min-w-0">
              <p className="text-body-sm font-medium text-foreground leading-tight truncate">
                {alert.facility_name || 'Unknown Facility'}
              </p>
              <p className="text-caption text-muted-foreground mt-0.5 truncate">{alert.district_name}</p>
            </div>
          </div>
          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded uppercase tracking-wider leading-none shrink-0 ${sev.color} ${sev.bg}`}>
            {sev.label}
          </span>
        </div>

        {/* Description */}
        {alert.what_is_happening && (
          <p className="text-caption text-muted-foreground leading-relaxed line-clamp-2 mb-2">
            {alert.what_is_happening}
          </p>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 min-w-0">
            {alert.rule_name && (
              <span className="text-[10px] font-medium text-muted-foreground bg-secondary px-1.5 py-0.5 rounded truncate max-w-[120px]">
                {alert.rule_name}
              </span>
            )}
            {alert.llm_generated && (
              <span className="text-[10px] font-semibold text-accent bg-accent/10 px-1.5 py-0.5 rounded">
                AI
              </span>
            )}
          </div>
          <span className="text-[11px] text-muted-foreground/70 shrink-0 ml-2">{timeAgo(alert.created_at)}</span>
        </div>

        {/* Expanded content */}
        {expanded && (
          <div className="mt-2.5 pt-2.5 border-t border-border/40 space-y-2 animate-fade-in">
            {alert.why_it_happening && (
              <div>
                <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider block mb-0.5">Root Cause</span>
                <p className="text-caption text-foreground/80 leading-relaxed">{alert.why_it_happening}</p>
              </div>
            )}
            {alert.recommended_action && (
              <div className="px-2.5 py-2 rounded-md bg-info/8 border border-info/20">
                <span className="text-[10px] font-semibold text-info uppercase tracking-wider block mb-0.5">Recommended Action</span>
                <p className="text-caption text-foreground/80 leading-relaxed">{alert.recommended_action}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
