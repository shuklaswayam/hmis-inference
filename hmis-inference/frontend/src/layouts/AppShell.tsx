import { useState, useEffect } from 'react'
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Activity,
  Search,
  Sun,
  Moon,
  ChevronRight,
  Terminal,
  Settings,
  ShieldAlert,
  LayoutDashboard,
  Brain,
  Info,
  HelpCircle,
  X,
  MessageSquare,
  LogOut,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { CommandPalette } from '@/components/layout/CommandPalette'
import { AIChat } from '@/components/AIChat'
import { SSEToastHost } from '@/components/SSEToastHost'
import { useAuth } from '@/auth/AuthContext'
import { useI18n, LanguageSwitcher } from '@/i18n'

export function AppShell() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const [isSidebarHovered, setIsSidebarHovered] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [aiChatOpen, setAiChatOpen] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [theme, setTheme] = useState<'light' | 'dark'>('dark')

  // Theme Management
  useEffect(() => {
    const saved = localStorage.getItem('hmis:theme') as 'light' | 'dark'
    if (saved) setTheme(saved)
  }, [])

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'dark') root.classList.add('dark')
    else root.classList.remove('dark')
    localStorage.setItem('hmis:theme', theme)
  }, [theme])

  // Keyboard navigation listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen(o => !o)
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'i') {
        e.preventDefault()
        setInspectorOpen(o => !o)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  const { t } = useI18n()
  const NAV_ITEMS_RAW = [
    { key: 'shell.nav.dashboard',  to: '/',           icon: LayoutDashboard },
    { key: 'shell.nav.facilities', to: '/facilities', icon: Activity       },
    { key: 'shell.nav.analytics',  to: '/analytics',  icon: Terminal       },
    { key: 'shell.nav.audit',      to: '/audit',      icon: ShieldAlert    },
    { key: 'shell.nav.settings',   to: '/settings',   icon: Settings       },
  ]
  const navItems = NAV_ITEMS_RAW.map((item) => ({ ...item, label: t(item.key) }))

  const isNavActive = (to: string) => {
    if (to === '/') return pathname === '/'
    return pathname.startsWith(to)
  }

  // Generate Breadcrumbs
  const getBreadcrumbs = () => {
    const segments = pathname.split('/').filter(Boolean)
    if (segments.length === 0) return [{ label: 'Executive Intelligence', href: '/' }]
    return [
      { label: 'Home', href: '/' },
      ...segments.map((seg, i) => ({
        label: seg.charAt(0).toUpperCase() + seg.slice(1),
        href: '/' + segments.slice(0, i + 1).join('/'),
      })),
    ]
  }

  const breadcrumbs = getBreadcrumbs()

  return (
    <div className="flex min-h-screen bg-background text-foreground selection:bg-accent/20 transition-colors duration-200">
      
      {/* 1. Left Sidebar */}
      <aside
        aria-label="Navigation sidebar"
        onMouseEnter={() => setIsSidebarHovered(true)}
        onMouseLeave={() => setIsSidebarHovered(false)}
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex flex-col bg-sidebar text-sidebar-foreground border-r border-sidebar-border/40',
          'transition-all duration-150 ease-out',
          (sidebarCollapsed && !isSidebarHovered) ? 'w-[64px]' : 'w-[240px]'
        )}
      >
        {/* Header/Logo */}
        <div className="flex items-center gap-3 h-12 px-4 select-none border-b border-sidebar-border/30">
          <div className="relative h-6 w-6 shrink-0 rounded bg-accent grid place-items-center">
            <Activity className="h-3.5 w-3.5 text-background" />
            <span className="absolute -top-0.5 -right-0.5 h-1.5 w-1.5 rounded-full bg-emerald-400 ring-1 ring-sidebar" />
          </div>
          {(!sidebarCollapsed || isSidebarHovered) && (
            <motion.div
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.12 }}
              className="flex flex-col leading-none"
            >
              <span className="text-body-sm font-semibold tracking-tight text-sidebar-foreground">Artem</span>
              <span className="text-[9px] tracking-widest text-sidebar-muted uppercase mt-0.5">Gujarat HMIS</span>
            </motion.div>
          )}
        </div>

        {/* Navigation Items */}
        <nav className="flex-1 px-2.5 py-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon
            const active = isNavActive(item.to)
            return (
              <Link
                key={item.to}
                to={item.to}
                className={cn(
                  'relative flex items-center h-9 rounded-md text-body-sm transition-all duration-100 outline-none',
                  active 
                    ? 'text-sidebar-foreground bg-white/[0.04]' 
                    : 'text-sidebar-muted hover:text-sidebar-foreground hover:bg-white/[0.02]'
                )}
              >
                {/* 3px vertical accent bar */}
                {active && (
                  <span className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r bg-accent" />
                )}

                <div className="w-[40px] shrink-0 flex justify-center">
                  <Icon className={cn('h-4 w-4 transition-colors', active ? 'text-accent' : 'text-sidebar-muted')} />
                </div>

                {(!sidebarCollapsed || isSidebarHovered) && (
                  <motion.span
                    initial={{ opacity: 0, x: -4 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.12 }}
                    className="flex-1 truncate font-medium text-left"
                  >
                    {item.label}
                  </motion.span>
                )}

                {(!sidebarCollapsed || isSidebarHovered) && (item as { badge?: string }).badge && (
                  <span className="mr-3 px-1.5 py-0.2 rounded text-[10px] font-mono font-semibold bg-accent/10 text-accent border border-accent/20">
                    {(item as { badge?: string }).badge}
                  </span>
                )}
              </Link>
            )
          })}
        </nav>

        {/* Footer info ribbon */}
        {(!sidebarCollapsed || isSidebarHovered) && (
          <div className="p-3 m-2.5 rounded-lg bg-white/[0.02] border border-sidebar-border/30">
            <div className="flex gap-2">
              <Brain className="h-3.5 w-3.5 text-accent shrink-0 mt-0.5" />
              <div className="flex flex-col leading-tight">
                <span className="text-[10px] font-medium text-sidebar-foreground">Inference engine</span>
                <span className="text-[9px] text-sidebar-muted">98.4% diagnostic accuracy</span>
              </div>
            </div>
          </div>
        )}

        {/* Sidebar Collapse Toggle Button at Bottom */}
        <button
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          className="flex items-center justify-center h-10 w-full border-t border-sidebar-border/30 text-sidebar-muted hover:text-sidebar-foreground transition-colors hover:bg-white/[0.02]"
        >
          <ChevronRight className={cn('h-4 w-4 transition-transform duration-200', !sidebarCollapsed && 'rotate-180')} />
        </button>
      </aside>

      {/* Main Container Wrapper */}
      <div 
        className={cn(
          'flex-1 flex flex-col min-w-0 transition-all duration-150 ease-out',
          (sidebarCollapsed && !isSidebarHovered) ? 'pl-[64px]' : 'pl-[240px]'
        )}
      >
        
        {/* 2. Top Bar (Ultra-thin 48px) */}
        <header className="sticky top-0 z-30 h-12 flex items-center justify-between px-6 border-b border-border/40 bg-background/80 backdrop-blur-md">
          {/* Left Breadcrumbs */}
          <div className="flex items-center gap-1.5 text-caption font-medium select-none">
            {breadcrumbs.map((crumb, idx) => (
              <div key={crumb.href} className="flex items-center gap-1.5">
                {idx > 0 && <span className="text-muted-foreground/40 font-normal">/</span>}
                <Link 
                  to={crumb.href} 
                  className={cn(
                    'transition-colors hover:text-foreground',
                    idx === breadcrumbs.length - 1 ? 'text-foreground' : 'text-muted-foreground'
                  )}
                >
                  {crumb.label}
                </Link>
              </div>
            ))}
          </div>

          {/* Right actions */}
          <div className="flex items-center gap-2">
            
            {/* Command Palette Trigger */}
            <button
              onClick={() => setPaletteOpen(true)}
              className="flex items-center gap-2 h-7 px-2.5 rounded border border-border/80 bg-secondary/30 text-muted-foreground hover:bg-secondary/60 hover:text-foreground transition-colors outline-none"
            >
              <Search className="h-3 w-3" />
              <span className="text-[11px] font-sans">Command menu</span>
              <kbd className="text-[9px] font-mono opacity-60 bg-background border border-border/40 px-1 rounded">⌘K</kbd>
            </button>

            

            {/* Language switcher — Phase 6 i18n (en/hi/gu). */}
            <LanguageSwitcher />{/* Dark / Light Toggle */}
            <button
              onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
              className="h-7 w-7 rounded border border-border/40 hover:bg-secondary/40 flex items-center justify-center transition-colors text-muted-foreground hover:text-foreground"
              aria-label="Toggle theme"
            >
              {theme === 'dark' ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
            </button>

            {/* AI Chat Toggle */}
            <button
              onClick={() => setAiChatOpen(!aiChatOpen)}
              className={cn(
                'h-7 w-7 rounded border flex items-center justify-center transition-all',
                aiChatOpen
                  ? 'border-accent/40 bg-accent/10 text-accent'
                  : 'border-border/40 hover:bg-secondary/40 text-muted-foreground hover:text-foreground'
              )}
              aria-label="Toggle AI chat"
            >
              <MessageSquare className="h-3.5 w-3.5" />
            </button>

            {/* Right Inspector Toggle */}
            <button
              onClick={() => setInspectorOpen(!inspectorOpen)}
              className={cn(
                'h-7 w-7 rounded border flex items-center justify-center transition-all',
                inspectorOpen 
                  ? 'border-accent/40 bg-accent/10 text-accent' 
                  : 'border-border/40 hover:bg-secondary/40 text-muted-foreground hover:text-foreground'
              )}
              aria-label="Toggle inspector"
            >
              <Info className="h-3.5 w-3.5" />
            </button>
          

            {user ? (
              <div
                className="flex items-center gap-1.5 h-7 px-2 rounded border border-border/40 bg-secondary/30 text-muted-foreground"
                aria-label="account chip"
              >
                <span className="text-[10px] tracking-wider uppercase font-semibold">
                  {user.full_name.split(' ')[0] || user.email}
             </span>
                <span className="text-[9px] tracking-widest uppercase text-muted-foreground/80">
                  {user.role}
             </span>
                <button
                  type="button"
                  onClick={() => { logout(); navigate('/login', { replace: true }) }}
                  className="h-5 w-5 rounded hover:bg-secondary/60 grid place-items-center text-muted-foreground hover:text-foreground"
                  aria-label="Sign out"
                  title="Sign out"
                >
                  <LogOut className="h-3 w-3" />
             </button>
            </div>
            ) : null}
         </div>
        </header>

        {/* Center Canvas */}
        <main className="flex-1 min-w-0 p-6 lg:p-8">
          <div className="mx-auto w-full max-w-[1200px]">
            <Outlet />
          </div>
        </main>
      </div>

      {/* SSE Toast Host — overlays the canvas when a CRITICAL
                transition arrives via /api/v1/realtime/events. */}
      <SSEToastHost />

      {/* 3. Optional Right Inspector Drawer */}
      <AnimatePresence>
        {inspectorOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.12 }}
              onClick={() => setInspectorOpen(false)}
              className="fixed inset-0 z-40 bg-background/20 backdrop-blur-[2px]"
            />
            <motion.aside
              initial={{ x: 320 }}
              animate={{ x: 0 }}
              exit={{ x: 320 }}
              transition={{ type: 'spring', stiffness: 380, damping: 32 }}
              className="fixed inset-y-0 right-0 z-50 w-[320px] bg-card border-l border-border/40 p-5 flex flex-col"
            >
              <div className="flex items-center justify-between pb-4 border-b border-border/40">
                <div className="flex items-center gap-2">
                  <HelpCircle className="h-4 w-4 text-accent" />
                  <span className="text-body-sm font-semibold">Workspace Inspector</span>
                </div>
                <button
                  onClick={() => setInspectorOpen(false)}
                  className="h-6 w-6 rounded hover:bg-secondary flex items-center justify-center transition-colors"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              {/* Inspector Content */}
              <div className="flex-1 py-4 overflow-y-auto space-y-4 text-body-sm">
                <div>
                  <h4 className="text-caption font-semibold text-muted-foreground uppercase tracking-wider">Keyboard shortcuts</h4>
                  <div className="mt-2 space-y-1.5 font-mono text-[11px]">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Search Palette</span>
                      <kbd className="bg-secondary px-1.5 rounded">⌘ K</kbd>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Inspector Toggle</span>
                      <kbd className="bg-secondary px-1.5 rounded">⌘ I</kbd>
                    </div>
                  </div>
                </div>

                <div className="pt-2 border-t border-border/30">
                  <h4 className="text-caption font-semibold text-muted-foreground uppercase tracking-wider">Platform Status</h4>
                  <div className="mt-2 space-y-2">
                    <div className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      <span className="text-[12px] text-muted-foreground">Backend API: Online</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      <span className="text-[12px] text-muted-foreground">Inference Pipeline: Idle</span>
                    </div>
                  </div>
                </div>
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* AI Chat Side Panel — 300px slide-in */}
      <div
        className={cn(
          'fixed inset-y-0 right-0 z-50 w-[300px] flex flex-col border-l border-border/40 shadow-2xl',
          'transition-transform duration-300 ease-in-out',
          aiChatOpen ? 'translate-x-0' : 'translate-x-full'
        )}
        aria-label="AI Chat panel"
      >
        <AIChat onClose={() => setAiChatOpen(false)} />
      </div>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </div>
  )
}
