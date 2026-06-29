/* eslint-disable @typescript-eslint/no-explicit-any */
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { ChevronRight, Filter, FileSearch, X, Download } from 'lucide-react'

import client from '@/api/client'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

async function downloadDigest(format: 'md' | 'json', window: string, filters: Record<string, string>) {
  const params: Record<string, string> = { format, window }
  Object.entries(filters).forEach(([k, v]) => {
    if (v) params[k] = v
  })
  // The backend isn't behind nginx yet for SSE, but download needs the same base URL.
  const baseURL = client.defaults.baseURL || ''
  const url = `${baseURL}/api/v1/inference/audit/digest?${new URLSearchParams(params).toString()}`
  // The MD path uses apiKey from axios defaults; cross-tab fetch would
  // miss that — so wire it in explicitly.
  const apiKey = (import.meta as any).env?.VITE_API_KEY?.trim?.() ?? ''
  const res = await fetch(url, {
    headers: apiKey ? { 'X-API-Key': apiKey } : {},
  })
  if (!res.ok) throw new Error(`digest ${format} failed (${res.status})`)
  const blob = await res.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `hmis-digest-${window}.${format === 'md' ? 'md' : 'json'}`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(a.href)
}

const WORKSTREAMS = [
  '',
  'outbreak_risk',
  'hospital_pressure',
  'priority_rank',
  'policy_memo',
] as const

const SEVERITIES = ['', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const

const WINDOWS = [
  { value: '1h',  label: '1 h' },
  { value: '24h', label: '24 h' },
  { value: '7d',  label: '7 d' },
  { value: '30d', label: '30 d' },
] as const

interface AuditRow {
  id: string
  workstream: string
  trace_id: string
  severity: string | null
  confidence: number | null
  generated_at: string | null
  expires_at: string | null
  request: Record<string, any>
  response: Record<string, any>
  district_id?: string | null
  facility_id?: string | null
}

export default function AuditLogPage() {
  const [workstream, setWorkstream] = useState<string>('')
  const [severity, setSeverity] = useState<string>('')
  const [window, setWindow] = useState<string>('24h')
  const [openRowId, setOpenRowId] = useState<string | null>(null)

  const query = useQuery<{ rows: AuditRow[]; count: number; now: string }>({
    queryKey: ['audit', workstream, severity, window],
    queryFn: async ({ signal }) => {
      const params: Record<string, string> = { window }
      if (workstream) params.workstream = workstream
      if (severity) params.severity = severity
      const res = await client.get('/api/v1/inference/audit/', { params, signal })
      return res.data
    },
    staleTime: 60 * 1000,
    refetchInterval: 60 * 1000,
  })

  const rows = query.data?.rows ?? []

  const grouped = useMemo(() => {
    const map = new Map<string, number>()
    rows.forEach((r) => {
      const k = `${r.workstream}::${r.severity ?? 'NONE'}`
      map.set(k, (map.get(k) ?? 0) + 1)
    })
    return Array.from(map.entries()).sort()
  }, [rows])

  return (
    <section className="animate-fade-in space-y-5">
      <header className="space-y-1">
        <span className="text-[10px] tracking-widest uppercase font-semibold text-muted-foreground">
          Weekly Review
       </span>
        <h1 className="text-heading-lg font-bold tracking-tight">
          Inference Audit Log
       </h1>
        <p className="text-body-sm text-muted-foreground">
          Every call to /api/v1/inference/* persists a row here — useful
          for the Commissioner&apos;s weekly review and for comparing a
          recompute against its predecessor.
       </p>
     </header>

      {/* Filters */}
      <Card className="p-4 border-border/80 flex flex-wrap items-center gap-3 bg-card/60 backdrop-blur-md">
        <Filter className="h-4 w-4 text-muted-foreground" />
        <label className="text-[11px] uppercase tracking-wider font-medium text-muted-foreground">
          Workstream
       </label>
        <select
          value={workstream}
          onChange={(e) => setWorkstream(e.target.value)}
          className="h-8 px-2 rounded border border-border/80 bg-card text-[12px] outline-none focus:border-accent"
        >
          {WORKSTREAMS.map((ws) => (
            <option key={ws || 'all'} value={ws}>{ws || 'all'}</option>
          ))}
       </select>
        <label className="text-[11px] uppercase tracking-wider font-medium text-muted-foreground">
          Severity
       </label>
        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
          className="h-8 px-2 rounded border border-border/80 bg-card text-[12px] outline-none focus:border-accent"
        >
          {SEVERITIES.map((s) => (
            <option key={s || 'all'} value={s}>{s || 'all'}</option>
          ))}
       </select>
        <div className="flex items-center gap-1 bg-secondary/40 p-0.5 rounded-md">
          {WINDOWS.map((w) => (
            <button
              key={w.value}
              type="button"
              onClick={() => setWindow(w.value)}
              className={cn(
                'px-2.5 py-1 text-[11px] font-medium rounded transition-all',
                window === w.value
                  ? 'bg-card text-foreground border border-border/40'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {w.label}
           </button>
          ))}
       </div>
        <span className="ml-auto text-[11px] text-muted-foreground">
          {query.isLoading ? 'Loading…' : `${query.data?.count ?? rows.length} rows`}
       </span>
          <DownloadDigestButton window={window} ws={workstream} sev={severity} format="md" />
          <DownloadDigestButton window={window} ws={workstream} sev={severity} format="json" />
     </Card>

      {/* Distribution strip */}
      {!query.isLoading && grouped.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {grouped.map(([k, c]) => {
            const [ws, sev] = k.split('::')
            return (
              <Badge key={k} variant="secondary" size="sm" className="text-[10px]">
                {ws} · {sev} · {c}
             </Badge>
            )
          })}
       </div>
      ) : null}

      {/* Row table */}
      <Card className="border-border/80 bg-card/60 backdrop-blur-md divide-y divide-border/30 overflow-hidden">
        {query.isLoading ? (
          <div className="p-4 space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-6 w-full opacity-[0.06]" />
            ))}
         </div>
        ) : rows.length === 0 ? (
          <div className="p-8 text-center text-muted-foreground text-[12px] space-y-2">
            <FileSearch className="h-7 w-7 mx-auto text-muted-foreground/40" />
            <p>No audit rows match the current filters</p>
            <p className="text-[11px]">
              Try widening the time window or clearing severity.
           </p>
         </div>
        ) : (
          rows.map((row) => (
            <div key={row.id} className="hover:bg-secondary/20 transition-colors">
              <button
                type="button"
                className="w-full text-left px-4 py-3 flex items-center gap-3"
                onClick={() => setOpenRowId(openRowId === row.id ? null : row.id)}
              >
                <ChevronRight
                  className={cn(
                    'h-3.5 w-3.5 text-muted-foreground transition-transform shrink-0',
                    openRowId === row.id && 'rotate-90',
                  )}
                />
                <span className="font-mono text-[11px] text-muted-foreground shrink-0">
                  {row.trace_id.slice(0, 8)}
               </span>
                <Badge variant="secondary" size="sm" className="text-[10px]">
                  {row.workstream}
               </Badge>
                {row.severity ? (
                  <Badge
                    variant={row.severity === 'CRITICAL' ? 'critical' : row.severity === 'HIGH' ? 'warning' : 'secondary'}
                    size="sm"
                  >
                    {row.severity}
                 </Badge>
                ) : null}
                <span className="text-[12px] text-foreground truncate flex-1">
                  {summariseRow(row)}
               </span>
                <span className="text-[10px] text-muted-foreground shrink-0">
                  {row.generated_at ? new Date(row.generated_at).toLocaleString() : '—'}
               </span>
             </button>
              {openRowId === row.id ? <JsonDrawer row={row} onClose={() => setOpenRowId(null)} /> : null}
           </div>
          ))
        )}
     </Card>
   </section>
  )
}

function summariseRow(row: AuditRow): string {
  const data = row.response ?? {}
  if (row.workstream === 'priority_rank' && Array.isArray(data?.ranked) && data.ranked[0]) {
    return `rank 1: ${data.ranked[0].headline ?? '—'}`
  }
  if (row.workstream === 'outbreak_risk' && Array.isArray(data?.signals)) {
    return `${data.signals.length} signal(s)`
  }
  if (row.workstream === 'hospital_pressure' && Array.isArray(data?.signals)) {
    const crit = data.signals.filter((s: any) => s.tier === 'Critical').length
    return `${data.signals.length} facilities · ${crit} critical`
  }
  if (row.workstream === 'policy_memo') {
    return data.headline ?? '—'
  }
  return row.workstream
}

function JsonDrawer({ row, onClose }: { row: AuditRow; onClose: () => void }) {
  return (
    <div className="border-t border-border/30 bg-secondary/20 px-4 py-4 space-y-3 text-[12px]">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">
          Request · Response
       </span>
        <Button size="sm" variant="secondary" onClick={onClose}>
          <X className="h-3 w-3" />
       </Button>
     </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <h4 className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground mb-1">
            Request
         </h4>
          <pre className="text-[11px] font-mono whitespace-pre-wrap rounded-md border border-border/40 bg-card/80 p-2 max-h-64 overflow-auto">
{JSON.stringify(row.request ?? {}, null, 2)}
         </pre>
       </div>
        <div>
          <h4 className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground mb-1">
            Response (preview)
         </h4>
          <pre className="text-[11px] font-mono whitespace-pre-wrap rounded-md border border-border/40 bg-card/80 p-2 max-h-64 overflow-auto">
{JSON.stringify(row.response ?? {}, null, 2)}
         </pre>
       </div>
     </div>
   </div>
  )
}

function DownloadDigestButton({ window, ws, sev, format }: { window: string; ws: string; sev: string; format: "md" | "json" }) {
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await downloadDigest(format, window, { workstream: ws, severity: sev })
        } catch (err) {
          console.error('digest export failed', err)
        }
      }}
      className="h-6 px-2 text-[10px] uppercase tracking-wider rounded border border-border/60 text-muted-foreground hover:text-foreground hover:bg-secondary/60 inline-flex items-center gap-1"
      aria-label={`Export digest as ${format}`}
    >
      <Download className="h-3 w-3" />
      {format.toUpperCase()}
 </button>
  )
}

