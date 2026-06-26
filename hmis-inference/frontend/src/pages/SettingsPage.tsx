import { useState } from 'react'
import { Settings, Save, Database, Bell, Shield, Palette, Globe } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'

// Display-only strings — env-driven at build time, kept visible so operators
// can see which backend/reverse-proxy they are currently pointing at.
const API_BASE_DISPLAY = (
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
).replace(/\/+$/, '')
const REDIS_DISPLAY =
  (import.meta.env.VITE_REDIS_URL || 'redis://localhost:6379/0').replace(
    /\/+$/,
    '',
  )
const CORS_DISPLAY =
  import.meta.env.VITE_ALLOWED_ORIGINS_DISPLAY ||
  'http://localhost:3000, http://localhost:5173'

const SECTIONS = [
  { id: 'general', label: 'General', icon: Settings },
  { id: 'data', label: 'Data Sources', icon: Database },
  { id: 'notifications', label: 'Notifications', icon: Bell },
  { id: 'security', label: 'Security', icon: Shield },
  { id: 'appearance', label: 'Appearance', icon: Palette },
  { id: 'integrations', label: 'Integrations', icon: Globe },
] as const

function Toggle({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: string
  description?: string
}) {
  return (
    <div className="flex items-center justify-between py-3">
      <div>
        <div className="text-body-sm font-medium text-foreground">{label}</div>
        {description && <div className="text-caption text-muted-foreground mt-0.5">{description}</div>}
      </div>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={cn(
          'relative h-5 w-9 rounded-full transition-colors',
          checked ? 'bg-accent' : 'bg-muted',
        )}
      >
        <span
          className={cn(
            'absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform',
            checked && 'translate-x-4',
          )}
        />
      </button>
    </div>
  )
}

export default function SettingsPage() {
  const [activeSection, setActiveSection] = useState('general')
  const [notifications, setNotifications] = useState({
    emailAlerts: true,
    criticalOnly: false,
    weeklyDigest: true,
    aiBriefings: true,
  })
  const [appearance, setAppearance] = useState({
    compactMode: false,
    animations: true,
    showConfidence: true,
  })

  return (
    <section className="animate-fade-in">
      <PageHeader
        eyebrow="Configuration"
        title="Settings"
        description="Workspace, integrations, and data-source configuration."
        actions={
          <Button size="sm">
            <Save className="h-3.5 w-3.5 mr-1.5" />
            Save Changes
          </Button>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[200px_1fr] min-h-[500px]">
        {/* Sidebar nav */}
        <nav className="space-y-0.5">
          {SECTIONS.map((s) => {
            const Icon = s.icon
            return (
              <button
                key={s.id}
                onClick={() => setActiveSection(s.id)}
                className={cn(
                  'w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-body-sm transition-colors text-left',
                  activeSection === s.id
                    ? 'bg-accent/10 text-accent font-medium'
                    : 'text-muted-foreground hover:text-foreground hover:bg-secondary/60',
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {s.label}
              </button>
            )
          })}
        </nav>

        {/* Content */}
        <Card className="p-6 border-border/80">
          {activeSection === 'general' && (
            <div className="space-y-6 animate-fade-in">
              <div>
                <h3 className="text-subheading font-semibold text-foreground mb-1">General Settings</h3>
                <p className="text-body-sm text-muted-foreground">Configure workspace preferences and defaults.</p>
              </div>
              <Separator />
              <div className="space-y-1">
                <label className="text-body-sm font-medium text-foreground">Workspace Name</label>
                <input
                  type="text"
                  defaultValue="Artem HMIS"
                  className="w-full h-9 px-3 rounded-md bg-secondary/60 border border-border text-body-sm text-foreground focus:outline-none focus:border-accent/40 focus:ring-1 focus:ring-accent/20"
                />
              </div>
              <div className="space-y-1">
                <label className="text-body-sm font-medium text-foreground">Default District</label>
                <select className="w-full h-9 px-3 rounded-md bg-secondary/60 border border-border text-body-sm text-foreground focus:outline-none focus:border-accent/40 appearance-none cursor-pointer">
                  <option>All Districts</option>
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-body-sm font-medium text-foreground">Timezone</label>
                <select className="w-full h-9 px-3 rounded-md bg-secondary/60 border border-border text-body-sm text-foreground focus:outline-none focus:border-accent/40 appearance-none cursor-pointer">
                  <option>Asia/Colombo (IST)</option>
                  <option>UTC</option>
                </select>
              </div>
            </div>
          )}

          {activeSection === 'data' && (
            <div className="space-y-6 animate-fade-in">
              <div>
                <h3 className="text-subheading font-semibold text-foreground mb-1">Data Sources</h3>
                <p className="text-body-sm text-muted-foreground">Configure backend connections and data refresh rates.</p>
              </div>
              <Separator />
              <div className="rounded-lg border border-border/60 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-body-sm font-medium text-foreground">Backend API</span>
                  <Badge variant="success" size="sm">Connected</Badge>
                </div>
                <p className="text-caption text-muted-foreground font-mono">{API_BASE_DISPLAY}</p>
              </div>
              <div className="rounded-lg border border-border/60 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-body-sm font-medium text-foreground">Redis Cache</span>
                  <Badge variant="success" size="sm">Connected</Badge>
                </div>
                <p className="text-caption text-muted-foreground font-mono">{REDIS_DISPLAY}</p>
              </div>
              <div className="rounded-lg border border-border/60 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-body-sm font-medium text-foreground">PostgreSQL</span>
                  <Badge variant="success" size="sm">Connected</Badge>
                </div>
                <p className="text-caption text-muted-foreground">Via DATABASE_URL env</p>
              </div>
              <div className="space-y-1">
                <label className="text-body-sm font-medium text-foreground">Alert Refresh Interval</label>
                <select className="w-full h-9 px-3 rounded-md bg-secondary/60 border border-border text-body-sm text-foreground focus:outline-none focus:border-accent/40 appearance-none cursor-pointer">
                  <option>30 seconds</option>
                  <option>60 seconds</option>
                  <option>5 minutes</option>
                </select>
              </div>
            </div>
          )}

          {activeSection === 'notifications' && (
            <div className="space-y-6 animate-fade-in">
              <div>
                <h3 className="text-subheading font-semibold text-foreground mb-1">Notifications</h3>
                <p className="text-body-sm text-muted-foreground">Control how and when you receive alerts.</p>
              </div>
              <Separator />
              <Toggle
                checked={notifications.emailAlerts}
                onChange={(v) => setNotifications((n) => ({ ...n, emailAlerts: v }))}
                label="Email Alerts"
                description="Receive critical alerts via email"
              />
              <Toggle
                checked={notifications.criticalOnly}
                onChange={(v) => setNotifications((n) => ({ ...n, criticalOnly: v }))}
                label="Critical Only"
                description="Only notify for HIGH severity alerts"
              />
              <Toggle
                checked={notifications.weeklyDigest}
                onChange={(v) => setNotifications((n) => ({ ...n, weeklyDigest: v }))}
                label="Weekly Digest"
                description="Receive a weekly summary of all activity"
              />
              <Toggle
                checked={notifications.aiBriefings}
                onChange={(v) => setNotifications((n) => ({ ...n, aiBriefings: v }))}
                label="AI Briefings"
                description="Get notified when AI intelligence reports are ready"
              />
            </div>
          )}

          {activeSection === 'security' && (
            <div className="space-y-6 animate-fade-in">
              <div>
                <h3 className="text-subheading font-semibold text-foreground mb-1">Security</h3>
                <p className="text-body-sm text-muted-foreground">Manage access and authentication settings.</p>
              </div>
              <Separator />
              <div className="rounded-lg border border-border/60 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-body-sm font-medium text-foreground">Authentication</span>
                  <Badge variant="warning" size="sm">Development Mode</Badge>
                </div>
                <p className="text-caption text-muted-foreground">
                  Authentication is disabled in development. Enable in production via environment variable.
                </p>
              </div>
              <div className="rounded-lg border border-border/60 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-body-sm font-medium text-foreground">CORS Origins</span>
                </div>
                <p className="text-caption text-muted-foreground font-mono">{CORS_DISPLAY}</p>
              </div>
            </div>
          )}

          {activeSection === 'appearance' && (
            <div className="space-y-6 animate-fade-in">
              <div>
                <h3 className="text-subheading font-semibold text-foreground mb-1">Appearance</h3>
                <p className="text-body-sm text-muted-foreground">Customize the look and feel of the interface.</p>
              </div>
              <Separator />
              <Toggle
                checked={appearance.compactMode}
                onChange={(v) => setAppearance((a) => ({ ...a, compactMode: v }))}
                label="Compact Mode"
                description="Reduce spacing and padding throughout the UI"
              />
              <Toggle
                checked={appearance.animations}
                onChange={(v) => setAppearance((a) => ({ ...a, animations: v }))}
                label="Animations"
                description="Enable page transitions and micro-interactions"
              />
              <Toggle
                checked={appearance.showConfidence}
                onChange={(v) => setAppearance((a) => ({ ...a, showConfidence: v }))}
                label="Show AI Confidence"
                description="Display confidence scores on alert cards"
              />
            </div>
          )}

          {activeSection === 'integrations' && (
            <div className="space-y-6 animate-fade-in">
              <div>
                <h3 className="text-subheading font-semibold text-foreground mb-1">Integrations</h3>
                <p className="text-body-sm text-muted-foreground">Connect external services and APIs.</p>
              </div>
              <Separator />
              <div className="rounded-lg border border-border/60 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-body-sm font-medium text-foreground">Artem AI Engine</span>
                  <Badge variant="success" size="sm">Active</Badge>
                </div>
                <p className="text-caption text-muted-foreground">LLM synthesis, RAG retrieval, and anomaly detection</p>
              </div>
              <div className="rounded-lg border border-border/60 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-body-sm font-medium text-foreground">Prophet Forecaster</span>
                  <Badge variant="success" size="sm">Active</Badge>
                </div>
                <p className="text-caption text-muted-foreground">Disease outbreak prediction with confidence intervals</p>
              </div>
              <div className="rounded-lg border border-dashed border-border/60 p-4 text-center">
                <p className="text-caption text-muted-foreground">More integrations coming soon</p>
              </div>
            </div>
          )}
        </Card>
      </div>
    </section>
  )
}
