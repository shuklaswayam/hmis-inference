import { useEffect, useState } from 'react'
import client from '@/api/client'

interface District {
  id: string
  name: string
}

interface DistrictFilterProps {
  value: string | null
  onChange: (v: string | null) => void
}

export function DistrictFilter({ value, onChange }: DistrictFilterProps) {
  const [districts, setDistricts] = useState<District[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    client
      .get('/api/v1/districts/')
      .then((res) => setDistricts(res.data || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="flex items-center gap-2">
      <label className="text-caption text-muted-foreground whitespace-nowrap">District</label>
      <div className="relative">
        <select
          value={value || ''}
          onChange={(e) => onChange(e.target.value || null)}
          disabled={loading}
          className="h-8 pl-3 pr-8 rounded-md bg-secondary/60 border border-border text-body-sm text-foreground focus:outline-none focus:border-accent/40 focus:ring-1 focus:ring-accent/20 cursor-pointer appearance-none transition-all hover:border-border disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <option value="">{loading ? 'Loading...' : 'All Districts'}</option>
          {districts.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
        <svg className="absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
          <path d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
        </svg>
      </div>
    </div>
  )
}
