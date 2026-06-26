import { AlertCard } from './AlertCard'

import type { Alert } from '@/types/alerts'

const FILTERS = [
  { key: 'ALL', label: 'All' },
  { key: 'HIGH', label: 'Critical' },
  { key: 'MEDIUM', label: 'Warning' },
  { key: 'LOW', label: 'Low' },
]

interface AlertFeedProps {
  alerts: Alert[]
  filter: string
  onFilterChange: (f: string) => void
  selectedAlert: Alert | null
  onSelectAlert: (a: Alert | null) => void
}

export function AlertFeed({ alerts, filter, onFilterChange, selectedAlert, onSelectAlert }: AlertFeedProps) {
  const filtered = filter === 'ALL' ? alerts : alerts.filter((a: any) => a.severity === filter)

  return (
    <div className="flex flex-col h-full">
      {/* Filter tabs */}
      <div className="px-4 py-3 border-b border-border/60">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-body-sm font-semibold text-foreground">Alert Feed</h2>
          <span className="text-caption text-muted-foreground bg-secondary px-2 py-0.5 rounded-md min-w-[28px] text-center leading-none">
            {filtered.length}
          </span>
        </div>
        <div className="flex gap-1 bg-secondary/60 rounded-lg p-0.5">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => onFilterChange(f.key)}
              className={`flex-1 px-3 py-1.5 text-caption font-medium rounded-md transition-all cursor-pointer ${
                filter === f.key
                  ? 'bg-background text-foreground shadow-soft-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full py-20 px-6">
            <div className="w-12 h-12 rounded-xl bg-secondary grid place-items-center mb-4">
              <svg className="w-6 h-6 text-muted-foreground/50" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                <path d="M9 14l2 2 4-4" />
              </svg>
            </div>
            <p className="text-body-sm font-medium text-muted-foreground mb-1">No alerts found</p>
            <p className="text-caption text-muted-foreground/70 text-center max-w-[200px]">Try changing the filter or district selection.</p>
          </div>
        ) : (
          <div className="p-2 space-y-1">
            {filtered.map((a: any) => (
              <AlertCard
                key={a.id}
                alert={a}
                isSelected={selectedAlert?.id === a.id}
                onSelect={onSelectAlert}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
