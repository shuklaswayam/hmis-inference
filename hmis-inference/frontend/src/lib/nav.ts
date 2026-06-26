import {
  LayoutDashboard,
  Siren,
  Search,
  Building2,
  LineChart,
  Sparkles,
  FileText,
  Settings,
  type LucideIcon,
} from 'lucide-react'

export interface NavItem {
  label: string
  to: string
  icon: LucideIcon
  shortcut?: string
  badge?: string
}

export const PRIMARY_NAV: NavItem[] = [
  { label: 'Overview', to: '/', icon: LayoutDashboard, shortcut: 'G O' },
  { label: 'Alerts', to: '/alerts', icon: Siren, shortcut: 'G A' },
  { label: 'Investigations', to: '/investigations', icon: Search, shortcut: 'G I' },
  { label: 'Facilities', to: '/facilities', icon: Building2, shortcut: 'G F' },
  { label: 'Analytics', to: '/analytics', icon: LineChart, shortcut: 'G N' },
]

export const INTELLIGENCE_NAV: NavItem[] = [
  { label: 'AI Intelligence', to: '/ai', icon: Sparkles, shortcut: 'G B' },
  { label: 'Reports', to: '/reports', icon: FileText, shortcut: 'G R' },
]

export const SECONDARY_NAV: NavItem[] = [
  { label: 'Settings', to: '/settings', icon: Settings, shortcut: 'G ,' },
]

export const ALL_NAV: NavItem[] = [...PRIMARY_NAV, ...INTELLIGENCE_NAV, ...SECONDARY_NAV]
