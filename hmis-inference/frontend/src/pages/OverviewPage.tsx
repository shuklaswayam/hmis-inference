import { useQuery } from '@tanstack/react-query'
import { useState, useEffect } from 'react'
import { 
  AlertTriangle, 
  Sparkles, 
  X, 
  TrendingUp, 
  Activity, 
  ShieldAlert, 
  Building2, 
  Check, 
  HelpCircle,
  Clock
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import client from '@/api/client'

// Simple helper to load Gujarat Map dynamically since Leaflet is client-side only
import GujaratMap from '@/components/GujaratMap'
import { cn } from '@/lib/utils'

interface Alert {
  id: number | string
  district_name: string
  facility_name: string
  severity: 'HIGH' | 'MEDIUM' | 'LOW'
  what_is_happening: string
  why_it_happening?: string
  recommended_action?: string
  created_at: string
  rule_name?: string
  llm_generated?: boolean
}

export default function OverviewPage() {
  const [districtId, setDistrictId] = useState<string | null>(null)
  const [selectedAlertId, setSelectedAlertId] = useState<number | string | null>(null)
  const [showAiRibbon, setShowAiRibbon] = useState(true)
  const [filter, setFilter] = useState<'ALL' | 'HIGH' | 'MEDIUM' | 'LOW'>('ALL')

  // Check if AI ribbon was dismissed in this session
  useEffect(() => {
    const dismissed = sessionStorage.getItem('hmis:ai-ribbon:dismissed')
    if (dismissed === 'true') setShowAiRibbon(false)
  }, [])

  const handleDismissAiRibbon = () => {
    setShowAiRibbon(false)
    sessionStorage.setItem('hmis:ai-ribbon:dismissed', 'true')
  }

  // Fetch alerts
  const { data: alerts = [], isLoading, isError, refetch } = useQuery<Alert[]>({
    queryKey: ['alerts', districtId],
    queryFn: async ({ signal }) => {
      const params: Record<string, string | number> = {}
      if (districtId) params.district_name = districtId
      const res = await client.get('/api/v1/alerts/', { params, signal })
      return (res.data ?? []) as Alert[]
    },
  })

  // Fetch district risk summary
  const { data: riskSummary = [] } = useQuery<{
    district_id: string
    district_name: string
    highest_severity: 'HIGH' | 'MEDIUM' | 'LOW' | 'NONE'
    alert_count: number
  }[]>({
    queryKey: ['districtRiskSummary'],
    queryFn: async ({ signal }) => {
      const res = await client.get('/api/v1/districts/risk-summary', { signal })
      return (res.data ?? []) as any[]
    },
  })

  // Filtered alerts
  const filteredAlerts = alerts.filter(a => filter === 'ALL' || a.severity === filter)

  // Compute metrics for the KPI block
  const totalAlerts = alerts.length
  const criticalAlerts = alerts.filter(a => a.severity === 'HIGH').length
  const warningAlerts = alerts.filter(a => a.severity === 'MEDIUM').length
  const uniqueFacilities = new Set(alerts.map(a => a.facility_name)).size

  return (
    <section className="space-y-6 animate-fade-in">
      
      {/* 1. AI Insight Ribbon */}
      <AnimatePresence>
        {showAiRibbon && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ type: 'spring', stiffness: 380, damping: 32 }}
            className="relative flex items-center justify-between gap-3 px-4 py-2.5 rounded-lg border border-accent/25 bg-accent/5 text-foreground select-none"
          >
            <div className="flex items-center gap-2 min-w-0">
              <Sparkles className="h-4 w-4 text-accent shrink-0" />
              <p className="text-[12px] font-medium leading-none truncate">
                OPD volume in Ahmedabad North is <span className="font-semibold text-accent">23% above 7-day baseline</span> — outbreak likelihood increased to moderate.
              </p>
            </div>
            <button
              onClick={handleDismissAiRibbon}
              className="h-5 w-5 rounded hover:bg-accent/10 flex items-center justify-center transition-colors text-muted-foreground hover:text-foreground"
              aria-label="Dismiss AI Insight"
            >
              <X className="h-3 w-3" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 2. Top Header Title Area */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <span className="text-[10px] tracking-widest text-muted-foreground uppercase font-semibold">Dashboard</span>
          <h1 className="text-heading-lg font-bold tracking-tight mt-0.5">Executive Health Intelligence</h1>
        </div>
        
        {/* Simple District Dropdown Filter */}
        <div className="flex items-center gap-2">
          <label htmlFor="district-select" className="text-caption text-muted-foreground">Focus District:</label>
          <select
            id="district-select"
            value={districtId ?? ''}
            onChange={(e) => setDistrictId(e.target.value || null)}
            className="h-8 px-2.5 rounded border border-border bg-card text-body-sm text-foreground outline-none focus:border-accent transition-colors"
          >
            <option value="">All Gujarat Districts</option>
            <option value="Ahmedabad">Ahmedabad</option>
            <option value="Surat">Surat</option>
            <option value="Vadodara">Vadodara</option>
            <option value="Rajkot">Rajkot</option>
            <option value="Bhavnagar">Bhavnagar</option>
          </select>
        </div>
      </div>

      {/* 3. Hero KPI Grid (4 Columns, Anchor Card is 2x width) */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Dominant Primary Metric Card (2x Weight) */}
        <Card className="col-span-1 md:col-span-2 p-5 border border-border bg-card/60 backdrop-blur-md flex flex-col justify-between h-36">
          <div className="flex items-start justify-between">
            <span className="text-caption text-muted-foreground font-medium uppercase tracking-wider">Operational Health Alerts</span>
            <ShieldAlert className="h-4 w-4 text-accent" />
          </div>
          <div className="mt-2 flex items-baseline gap-3">
            <span className="text-[40px] font-bold tracking-tight text-foreground leading-none font-sans">
              {isLoading ? '...' : totalAlerts}
            </span>
            <span className="text-caption text-emerald-400 font-semibold flex items-center gap-0.5">
              <TrendingUp className="h-3 w-3" /> +12% vs avg
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground mt-2">
            Primary operational indicator for regional hospital capacity and outbreak warning thresholds.
          </p>
        </Card>

        {/* Second Card (Critical) */}
        <Card className="p-5 border border-border bg-card/60 backdrop-blur-md flex flex-col justify-between h-36">
          <div className="flex items-start justify-between">
            <span className="text-caption text-muted-foreground font-medium uppercase tracking-wider">Critical</span>
            <span className="w-2 h-2 rounded-full bg-destructive" />
          </div>
          <div className="mt-2">
            <span className="text-display-lg font-bold text-foreground leading-none">
              {isLoading ? '...' : criticalAlerts}
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Requires immediate response from local medical officers.
          </p>
        </Card>

        {/* Third Card (Facilities) */}
        <Card className="p-5 border border-border bg-card/60 backdrop-blur-md flex flex-col justify-between h-36">
          <div className="flex items-start justify-between">
            <span className="text-caption text-muted-foreground font-medium uppercase tracking-wider">Facilities</span>
            <Building2 className="h-4 w-4 text-muted-foreground/60" />
          </div>
          <div className="mt-2">
            <span className="text-display-lg font-bold text-foreground leading-none">
              {isLoading ? '...' : uniqueFacilities}
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Distinct healthcare institutions currently reporting warning metrics.
          </p>
        </Card>
      </div>

      {/* 4. Gujarat Choropleth Map Component */}
      <div className="grid grid-cols-1 gap-6">
        <GujaratMap 
          districtId={districtId} 
          onDistrictClick={(name) => setDistrictId(name === districtId ? null : name)} 
          riskSummary={riskSummary}
        />
      </div>

      {/* 5. Live Alert Feed (No Clutter, 1-line rows, Spring Expand) */}
      <Card className="border border-border bg-card/50 backdrop-blur-md overflow-hidden">
        {/* Feed Header */}
        <div className="px-5 py-4 border-b border-border/40 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
            <h2 className="text-body-sm font-semibold tracking-tight text-foreground">Live Telemetry Alert Feed</h2>
          </div>
          
          {/* Segmented Filter Chips */}
          <div className="flex gap-1 bg-secondary/40 p-0.5 rounded">
            {(['ALL', 'HIGH', 'MEDIUM', 'LOW'] as const).map((lvl) => (
              <button
                key={lvl}
                onClick={() => setFilter(lvl)}
                className={cn(
                  'px-2.5 py-1 text-[11px] font-medium rounded transition-all',
                  filter === lvl 
                    ? 'bg-card text-foreground border border-border/40' 
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                {lvl}
              </button>
            ))}
          </div>
        </div>

        {/* Alert List Rows */}
        <div className="divide-y divide-border/30">
          {isLoading ? (
            <div className="p-5 space-y-3">
              <Skeleton className="h-6 w-full opacity-[0.06] animate-pulse" />
              <Skeleton className="h-6 w-3/4 opacity-[0.06] animate-pulse" />
              <Skeleton className="h-6 w-5/6 opacity-[0.06] animate-pulse" />
            </div>
          ) : isError ? (
            <div className="p-8 text-center text-muted-foreground text-body-sm">
              <AlertTriangle className="h-8 w-8 text-destructive mx-auto mb-2" />
              <p>Failed to retrieve system alerts.</p>
              <Button size="sm" onClick={() => refetch()} className="mt-4">Retry Connection</Button>
            </div>
          ) : filteredAlerts.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground text-body-sm">
              No alerts match the selected focus criteria.
            </div>
          ) : (
            filteredAlerts.map((alert, idx) => {
              const isSelected = selectedAlertId === alert.id
              const isCritical = alert.severity === 'HIGH'
              const isWarning = alert.severity === 'MEDIUM'

              return (
                <div 
                  key={alert.id}
                  className={cn(
                    'transition-colors duration-100 hover:bg-secondary/20',
                    isSelected && 'bg-secondary/40'
                  )}
                >
                  {/* Row Trigger */}
                  <div
                    onClick={() => setSelectedAlertId(isSelected ? null : alert.id)}
                    className="flex items-center justify-between px-5 py-3.5 cursor-pointer text-body-sm select-none"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      {/* Gutter State Glyph */}
                      <div className="shrink-0 flex items-center justify-center">
                        {isCritical ? (
                          <span className="w-2.5 h-2.5 rounded-full bg-destructive" title="Critical" />
                        ) : isWarning ? (
                          <span className="w-2.5 h-2.5 rounded-full bg-amber-400" title="Warning" />
                        ) : (
                          <span className="w-2.5 h-2.5 rounded-full bg-blue-400" title="Low" />
                        )}
                      </div>

                      {/* Title description */}
                      <span className="font-medium text-foreground truncate max-w-[280px] sm:max-w-md">
                        {alert.facility_name} — {alert.what_is_happening}
                      </span>
                    </div>

                    <div className="flex items-center gap-3 shrink-0">
                      {alert.llm_generated && (
                        <span className="text-[9px] font-bold text-accent bg-accent/10 px-1 py-0.2 rounded border border-accent/20">AI</span>
                      )}
                      <span className="text-caption text-muted-foreground flex items-center gap-1">
                        <Clock className="h-3 w-3" /> {new Date(alert.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                  </div>

                  {/* Dynamic Spring Detail Expand */}
                  <AnimatePresence initial={false}>
                    {isSelected && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ type: 'spring', stiffness: 380, damping: 32 }}
                        className="overflow-hidden bg-secondary/10 border-t border-border/20"
                      >
                        <div className="px-10 pb-5 pt-3 space-y-3 text-caption text-muted-foreground max-w-2xl">
                          {alert.why_it_happening && (
                            <div>
                              <span className="text-[10px] font-semibold uppercase tracking-wider text-foreground block mb-0.5">Root Cause Assessment</span>
                              <p className="leading-relaxed text-foreground/80">{alert.why_it_happening}</p>
                            </div>
                          )}
                          {alert.recommended_action && (
                            <div className="p-3 rounded border border-accent/20 bg-accent/5 text-foreground/90">
                              <span className="text-[10px] font-bold text-accent uppercase tracking-wider block mb-0.5">Recommended Actions</span>
                              <p className="leading-relaxed">{alert.recommended_action}</p>
                            </div>
                          )}
                          <div className="flex items-center gap-4 text-[10px] pt-1">
                            <span>District: <strong>{alert.district_name}</strong></span>
                            <span>Metric Trigger: <strong>{alert.rule_name ?? 'Static Rule'}</strong></span>
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )
            })
          )}
        </div>
      </Card>
    </section>
  )
}
