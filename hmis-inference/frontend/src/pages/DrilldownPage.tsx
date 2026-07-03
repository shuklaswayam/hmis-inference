import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ArrowLeft, AlertTriangle, Activity } from 'lucide-react'

import client from '@/api/client'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const SEV_STYLE: Record<string, string> = {
  Critical: 'text-destructive border-destructive/40 bg-destructive/10',
  Strained: 'text-warning border-warning/40 bg-warning/10',
  Normal:   'text-success border-success/40 bg-success/10',
}

export default function DrilldownPage() {
  const params = useParams<{ kind: string; id?: string; disease?: string }>()
  const kind = params.kind
  const id = params.id
  const disease = params.disease ?? ''

  if (kind === 'facility' && id) {
    return <FacilityDrilldown facilityId={id} />
  }
  if (kind === 'district' && id && disease) {
    return <DistrictDrilldown districtId={id} disease={disease} />
  }
  return (
    <section className="animate-fade-in space-y-3">
      <Link to="/" className="inline-flex items-center gap-1 text-[12px] text-accent hover:underline">
        <ArrowLeft className="h-3 w-3" />
        Back to dashboard
     </Link>
      <Card className="p-6 border-border/80 bg-card/60 text-center text-[12px] text-muted-foreground">
        <AlertTriangle className="h-6 w-6 mx-auto mb-2 text-warning" />
        Pick a facility from the Hospital Pressure widget or a (district ×
        disease) bucket from the Outbreak Risk widget to drill in.
     </Card>
   </section>
  )
}

interface FacilityDrilldownData {
  facility: { id: string; name: string; district: string; district_id: string }
  trajectory: {
    dates: string[]
    icu_pct: (number | null)[]
    bed_pct: (number | null)[]
    opd_visits: number[]
    emergency_visits: number[]
  }
  z_scores: Record<string, { mean: number; std: number; z_score_latest: number; latest: number }>
  projected_48h: {
    trend: 'rising' | 'stable' | 'easing' | null
    trend_confidence: number
    projection_available: boolean
    icu_24h: number | null
    icu_48h: number | null
    bed_48h: number | null
    series: { ds: string; icu_yhat: number; bed_yhat: number }[]
  }
}

function FacilityDrilldown({ facilityId }: { facilityId: string }) {
  const q = useQuery<FacilityDrilldownData>({
    queryKey: ['drilldown', 'facility', facilityId],
    queryFn: async ({ signal }) => {
      const res = await client.get(
        `/api/v1/inference/drilldown/facility/${facilityId}`,
        { signal },
      )
      return res.data as FacilityDrilldownData
    },
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  })

  if (q.isLoading) return <DrillSkeleton />
  if (q.isError || !q.data) {
    return (
      <Card className="p-6 border-border/80 bg-card/60 text-center text-[12px] text-destructive">
        Failed to load drilldown. Is the backend running?
     </Card>
    )
  }

  const d = q.data
  const chartData = d.trajectory.dates.map((date, idx) => ({
    date,
    icu: d.trajectory.icu_pct[idx],
    bed: d.trajectory.bed_pct[idx],
    icuProjection: d.projected_48h.series[idx]?.icu_yhat,
  }))
  const tier = pickTierClass(d.projected_48h.icu_48h, d.projected_48h.bed_48h)

  return (
    <section className="animate-fade-in space-y-4">
      <Link to="/" className="inline-flex items-center gap-1 text-[12px] text-accent hover:underline">
        <ArrowLeft className="h-3 w-3" />
        Back to dashboard
     </Link>

      <header className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <span className="text-[10px] tracking-widest uppercase font-semibold text-muted-foreground">
            Facility Drilldown
         </span>
          <h1 className="text-heading-lg font-bold tracking-tight">{d.facility.name}</h1>
          <p className="text-body-sm text-muted-foreground">{d.facility.district}</p>
       </div>
        <Badge variant="secondary" className={cn('text-[10px]', SEV_STYLE[tier] ?? '')}>
          {tier}
       </Badge>
     </header>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2 p-4 border-border/80 bg-card/60">
          <h2 className="text-subheading font-semibold tracking-tight mb-2 flex items-center gap-2">
            <Activity className="h-4 w-4 text-accent" />
            14-day trajectory + 48-h projection
         </h2>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="icuGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#ef4444" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#ef4444" stopOpacity={0.05} />
                 </linearGradient>
                  <linearGradient id="bedGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.05} />
                 </linearGradient>
               </defs>
                <CartesianGrid stroke="hsl(var(--border) / 0.3)" strokeDasharray="3 3" />
                <XAxis dataKey="date" stroke="#9ca3af" fontSize={10} />
                <YAxis stroke="#9ca3af" fontSize={10} domain={[0, 100]} unit="%" />
                <Tooltip
                  contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border) / 0.6)', borderRadius: 6, fontSize: 12 }}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Area type="monotone" dataKey="icu" stroke="#ef4444" fill="url(#icuGrad)" strokeWidth={1.5} name="ICU %" />
                <Area type="monotone" dataKey="bed" stroke="#3b82f6" fill="url(#bedGrad)" strokeWidth={1.5} name="Bed %" />
                <Line type="monotone" dataKey="icuProjection" stroke="#ef4444" strokeDasharray="4 4" strokeWidth={1.5} dot={false} name="ICU projection" />
             </AreaChart>
           </ResponsiveContainer>
         </div>
       </Card>

        <Card className="p-4 border-border/80 bg-card/60 space-y-3">
          <h2 className="text-subheading font-semibold tracking-tight">Z-scores</h2>
          <ul className="space-y-2 text-[12px]">
            {Object.entries(d.z_scores).map(([k, v]) => (
              <li key={k} className="border-b border-border/30 pb-2 last:border-b-0 last:pb-0">
                <div className="flex items-center justify-between">
                  <span className="text-foreground">{humanMetric(k)}</span>
                  <span
                    className={cn(
                      'font-mono text-[11px]',
                      Math.abs(v.z_score_latest) > 2 && 'text-destructive font-bold',
                    )}
                  >
                    z = {v.z_score_latest.toFixed(2)}
                 </span>
               </div>
                <p className="text-[10px] text-muted-foreground">
                  μ = {v.mean} · σ = {v.std} · latest = {v.latest}
               </p>
             </li>
            ))}
         </ul>
          <h2 className="text-subheading font-semibold tracking-tight pt-2">48-h forecast</h2>
          <div className="text-[12px] space-y-1">
            <p>Trend · <span className="font-medium">{d.projected_48h.trend ?? 'stable'}</span></p>
            <p>ICU @ 48 h · <span className="font-medium">{fmt(d.projected_48h.icu_48h)}%</span></p>
            <p>Bed @ 48 h · <span className="font-medium">{fmt(d.projected_48h.bed_48h)}%</span></p>
         </div>
       </Card>
     </div>
   </section>
  )
}

interface DistrictDrilldownData {
  district: { id: string; name: string }
  disease: string
  cases_last_14d: number
  deaths_last_14d: number
  baseline_avg: number
  baseline_ratio: number
  weekly_trend_slope: number
  series: { date: string; cases: number }[]
}

function DistrictDrilldown({ districtId, disease }: { districtId: string; disease: string }) {
  const q = useQuery<DistrictDrilldownData>({
    queryKey: ['drilldown', 'district', districtId, disease],
    queryFn: async ({ signal }) => {
      const res = await client.get(
        `/api/v1/inference/drilldown/district`,
        { params: { district_id: districtId, disease }, signal },
      )
      return res.data as DistrictDrilldownData
    },
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  })

  if (q.isLoading) return <DrillSkeleton />
  if (q.isError || !q.data) {
    return (
      <Card className="p-6 border-border/80 bg-card/60 text-center text-[12px] text-destructive">
        Failed to load drilldown. Is the backend running?
     </Card>
    )
  }
  const d = q.data
  const tier = ruleTier(d.baseline_ratio, d.deaths_last_14d)

  return (
    <section className="animate-fade-in space-y-4">
      <Link to="/" className="inline-flex items-center gap-1 text-[12px] text-accent hover:underline">
        <ArrowLeft className="h-3 w-3" />
        Back to dashboard
     </Link>
      <header className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <span className="text-[10px] tracking-widest uppercase font-semibold text-muted-foreground">
            District Drilldown
         </span>
          <h1 className="text-heading-lg font-bold tracking-tight">
            {d.disease} · {d.district.name}
         </h1>
       </div>
        <Badge variant="secondary" className={cn('text-[10px]', SEV_STYLE[tier] ?? '')}>
          {tier}
       </Badge>
     </header>
      <Card className="p-4 border-border/80 bg-card/60">
        <h2 className="text-subheading font-semibold tracking-tight mb-2">14-day case series</h2>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={d.series}>
              <CartesianGrid stroke="hsl(var(--border) / 0.3)" strokeDasharray="3 3" />
              <XAxis dataKey="date" stroke="#9ca3af" fontSize={10} />
              <YAxis stroke="#9ca3af" fontSize={10} allowDecimals={false} />
              <Tooltip contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border) / 0.6)', borderRadius: 6, fontSize: 12 }} />
              <Area type="monotone" dataKey="cases" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.3} name="Cases" />
           </AreaChart>
         </ResponsiveContainer>
       </div>
     </Card>
      <Card className="p-4 border-border/80 bg-card/60 grid grid-cols-2 md:grid-cols-4 gap-3 text-[12px]">
        <Stat label="Cases (14 d)" value={String(d.cases_last_14d)} />
        <Stat label="Deaths (14 d)" value={String(d.deaths_last_14d)} />
        <Stat label="Baseline avg" value={d.baseline_avg.toFixed(2)} />
        <Stat label="Baseline ratio" value={`${d.baseline_ratio.toFixed(2)}×`} />
     </Card>
   </section>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="text-[18px] font-semibold text-foreground leading-tight">{value}</p>
   </div>
  )
}

function DrillSkeleton() {
  return (
    <section className="space-y-3 animate-fade-in">
      <Skeleton className="h-6 w-32 opacity-30" />
      <Skeleton className="h-32 w-full opacity-30" />
      <Skeleton className="h-64 w-full opacity-30" />
   </section>
  )
}

function fmt(n: number | null | undefined): string {
  return n == null ? '—' : Number(n).toFixed(0)
}

function humanMetric(metric: string): string {
  if (metric === 'icu_pct') return 'ICU %'
  if (metric === 'bed_pct') return 'Bed %'
  if (metric === 'opd_visits') return 'OPD visits'
  if (metric === 'emergency_visits') return 'Emergency visits'
  return metric
}

function pickTierClass(icu48: number | null, bed48: number | null): 'Critical' | 'Strained' | 'Normal' {
  const icu = icu48 ?? 0
  const bed = bed48 ?? 0
  if (icu >= 90 || bed >= 95) return 'Critical'
  if (icu >= 80 || bed >= 85) return 'Strained'
  return 'Normal'
}

function ruleTier(baselineRatio: number, deaths: number): 'Critical' | 'High' | 'Medium' | 'Low' {
  if (baselineRatio >= 5 || deaths >= 3) return 'Critical'
  if (baselineRatio >= 4 || deaths >= 1) return 'High'
  if (baselineRatio >= 2) return 'Medium'
  return 'Low'
}
