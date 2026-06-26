import { useState, useEffect } from 'react'
import { MapContainer, TileLayer, GeoJSON } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'

interface DistrictRisk {
  district_id: string
  district_name: string
  highest_severity: 'HIGH' | 'MEDIUM' | 'LOW' | 'NONE'
  alert_count: number
}

interface GujaratMapProps {
  districtId?: string | null
  onDistrictClick: (districtName: string | null) => void
  riskSummary?: DistrictRisk[]
}

const GUJARAT_CENTER: [number, number] = [22.2587, 71.1924]

// Colors per checklist spec
const SEVERITY_COLORS = {
  HIGH: '#DC2626',     // Red
  MEDIUM: '#F97316',   // Orange
  LOW: '#16A34A',      // Green
  NONE: '#9CA3AF',     // Muted Gray
}

export default function GujaratMap({ districtId, onDistrictClick, riskSummary = [] }: GujaratMapProps) {
  const [geoJsonData, setGeoJsonData] = useState<any>(null)

  // Fetch the district GeoJSON polygons from public folder
  useEffect(() => {
    fetch('/gujarat_districts.json')
      .then((res) => res.json())
      .then((data) => setGeoJsonData(data))
      .catch((err) => console.error('Failed to load Gujarat districts GeoJSON:', err))
  }, [])

  // Find risk info for a given district name
  const getDistrictRisk = (name: string) => {
    return riskSummary.find((r) => r.district_name.toLowerCase() === name.toLowerCase())
  }

  // Dynamic styling for each district polygon
  const getFeatureStyle = (feature: any) => {
    const name = feature.properties.name
    const isSelected = districtId?.toLowerCase() === name.toLowerCase()
    const risk = getDistrictRisk(name)
    const severity = risk ? risk.highest_severity : 'NONE'
    
    return {
      fillColor: SEVERITY_COLORS[severity] || SEVERITY_COLORS.NONE,
      fillOpacity: isSelected ? 0.85 : 0.7,
      color: isSelected ? '#34D5C2' : 'white',
      weight: isSelected ? 3 : 1,
      opacity: 1,
      dashArray: isSelected ? '' : '',
    }
  }

  // Interactivity handlers for each polygon
  const onEachFeature = (feature: any, layer: any) => {
    const name = feature.properties.name
    const risk = getDistrictRisk(name)
    const severity = risk ? risk.highest_severity : 'NONE'
    const alertCount = risk ? risk.alert_count : 0

    // Bind rich HTML tooltip
    const dotColor =
      severity === 'HIGH' ? '#DC2626' :
      severity === 'MEDIUM' ? '#F97316' :
      severity === 'LOW' ? '#16A34A' : '#9CA3AF'

    const tooltipContent = `
      <div style="font-family: system-ui, sans-serif; padding: 4px 6px;">
        <div style="font-weight: 600; font-size: 13px; color: #1e293b;">${name}</div>
        <div style="display: flex; align-items: center; gap: 6px; margin-top: 4px;">
          <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background-color: ${dotColor};"></span>
          <span style="font-size: 11px; font-weight: 500; color: #475569;">${severity} Severity</span>
        </div>
        <div style="font-size: 11px; color: #64748b; margin-top: 2px;">${alertCount} Active Alerts</div>
      </div>
    `
    layer.bindTooltip(tooltipContent, {
      sticky: true,
      direction: 'auto',
      opacity: 0.95
    })

    // Hover effect and click handler
    layer.on({
      mouseover: (e: any) => {
        const l = e.target
        l.setStyle({
          fillOpacity: 0.7,
          weight: districtId?.toLowerCase() === name.toLowerCase() ? 3 : 2,
          opacity: 0.9
        })
      },
      mouseout: (e: any) => {
        const l = e.target
        // Reset to original feature style
        l.setStyle(getFeatureStyle(feature))
      },
      click: () => {
        onDistrictClick(name)
      }
    })
  }

  // Create unique key to force GeoJSON component update when selection or risk summaries change
  const geoJsonKey = `${districtId || 'all'}-${JSON.stringify(riskSummary)}`

  return (
    <div className="rounded-lg overflow-hidden border border-border bg-card/40 backdrop-blur-md relative">
      <div className="px-4 py-2.5 border-b border-border/40 flex items-center justify-between">
        <h2 className="text-body-sm font-semibold tracking-tight text-foreground">
          Gujarat Districts{districtId ? ` · ${districtId}` : ''}
        </h2>
        {districtId && (
          <button
            onClick={() => onDistrictClick(null)}
            className="text-caption text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Clear district filter"
          >
            Clear filter
          </button>
        )}
      </div>
      <div className="relative" style={{ height: 380 }}>
        <MapContainer
          center={GUJARAT_CENTER}
          zoom={7}
          style={{ height: '100%', width: '100%' }}
          scrollWheelZoom={false}
        >
          <TileLayer
            attribution='&copy; OpenStreetMap contributors &copy; CARTO'
            url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"
          />
          {geoJsonData && (
            <GeoJSON
              key={geoJsonKey}
              data={geoJsonData}
              style={getFeatureStyle}
              onEachFeature={onEachFeature}
            />
          )}
        </MapContainer>

        {/* Legend */}
        <div 
          className="absolute bottom-4 right-4 z-[400] bg-card/95 backdrop-blur-md border border-border p-2.5 rounded-md shadow-md text-[11px] font-medium space-y-1.5"
          style={{ minWidth: 100 }}
        >
          <div className="text-muted-foreground font-semibold text-[10px] uppercase tracking-wider mb-1">
            Severity
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: SEVERITY_COLORS.HIGH, opacity: 0.8 }} />
            <span className="text-foreground">High</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: SEVERITY_COLORS.MEDIUM, opacity: 0.8 }} />
            <span className="text-foreground">Medium</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: SEVERITY_COLORS.LOW, opacity: 0.8 }} />
            <span className="text-foreground">Low</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: SEVERITY_COLORS.NONE, opacity: 0.8 }} />
            <span className="text-foreground">No Alerts</span>
          </div>
        </div>
      </div>
    </div>
  )
}
