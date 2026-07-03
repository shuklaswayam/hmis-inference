import { useCallback, useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  ArrowUp, 
  Sparkles, 
  Loader2,
  Navigation,
  Flame,
  Search,
  Globe,
  Settings,
  ShieldAlert,
  Download,
  Eye,
  Tv,
  LayoutDashboard,
  Activity,
  Terminal
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { cn } from '@/lib/utils'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { 
  CommandDialog, 
  CommandEmpty, 
  CommandGroup, 
  CommandInput, 
  CommandItem, 
  CommandList,
  CommandSeparator
} from '@/components/ui/command'

type NavItem = { label: string; to: string; icon: typeof Sparkles }
type ActionItem = { label: string; action: string; icon: typeof Sparkles; shortcut?: string }
type CommandItemData = NavItem | ActionItem

interface AiCommandBarProps {
  onSubmit?: (prompt: string) => void
  placeholder?: string
  disabled?: boolean
}

export function AiCommandBar({
  onSubmit,
  placeholder = 'Ask Artem Intelligence…  (e.g., "Why is ICU occupancy rising in Surat?")',
  disabled = false,
}: AiCommandBarProps) {
  const [value, setValue] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const submit = useCallback(async () => {
    if (!value.trim() || disabled) return
    setSubmitting(true)
    try {
      await onSubmit?.(value.trim())
      setValue('')
    } finally {
      setSubmitting(false)
    }
  }, [value, onSubmit, disabled])

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
      className={cn(
        'group/ai relative flex items-center h-8 rounded border border-border bg-secondary/40 focus-within:bg-background focus-within:border-accent/40 transition-all duration-150',
      )}
    >
      <div className="grid place-items-center h-8 w-8 shrink-0 text-accent">
        <Sparkles className="h-3.5 w-3.5" />
      </div>
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        disabled={disabled || submitting}
        aria-label="AI command input"
        className="flex-1 bg-transparent text-xs text-foreground placeholder:text-muted-foreground/60 outline-none disabled:opacity-50"
      />
      <div className="pr-1.5">
        <Tooltip delayDuration={200}>
          <TooltipTrigger asChild>
            <button
              type="submit"
              disabled={!value.trim() || submitting}
              aria-label="Submit AI command"
              className={cn(
                'grid place-items-center h-6 w-6 rounded bg-foreground text-background transition-opacity',
                (!value.trim() || submitting) && 'opacity-20 cursor-not-allowed',
              )}
            >
              {submitting ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <ArrowUp className="h-3 w-3" />
              )}
            </button>
          </TooltipTrigger>
          <TooltipContent>Ask AI · ⏎</TooltipContent>
        </Tooltip>
      </div>
    </form>
  )
}

// ────────────────────────────────────────────────────────────
// Command Palette (⌘K)
// ────────────────────────────────────────────────────────────
interface CommandPaletteProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')

  // Reset search when palette closes
  useEffect(() => {
    if (!open) {
      setSearch('')
    }
  }, [open])

  const handleSelect = (to?: string, action?: string) => {
    onOpenChange(false)
    if (to) {
      navigate(to)
    } else if (action) {
      if (action === 'theme') {
        const root = document.documentElement
        const isDark = root.classList.contains('dark')
        if (isDark) {
          root.classList.remove('dark')
          localStorage.setItem('hmis:theme', 'light')
        } else {
          root.classList.add('dark')
          localStorage.setItem('hmis:theme', 'dark')
        }
      } else {
        alert(`Action executed: ${action}`)
      }
    }
  }

  const items: { group: string; items: CommandItemData[] }[] = [
    {
      group: 'Navigation',
      items: [
        { label: 'Overview Dashboard', to: '/', icon: LayoutDashboard },
        { label: 'Facilities', to: '/facilities', icon: Activity },
        { label: 'Analytics', to: '/analytics', icon: Terminal },
        { label: 'Audit Log', to: '/audit', icon: ShieldAlert },
        { label: 'Settings & Config', to: '/settings', icon: Settings },
      ]
    },
    {
      group: 'District Jumps',
      items: [
        { label: 'Go to Ahmedabad District', action: 'district-ahmedabad', icon: Globe },
        { label: 'Go to Surat District', action: 'district-surat', icon: Globe },
        { label: 'Go to Vadodara District', action: 'district-vadodara', icon: Globe },
        { label: 'Go to Rajkot District', action: 'district-rajkot', icon: Globe },
        { label: 'Go to Gandhinagar District', action: 'district-gandhinagar', icon: Globe },
      ]
    },
    {
      group: 'AI Actions',
      items: [
        { label: 'Trigger AI Briefing Report', action: 'briefing', icon: Sparkles, shortcut: 'B' },
        { label: 'Generate Outbreak Analysis Summary', action: 'summary', icon: Sparkles, shortcut: 'G' },
      ]
    },
    {
      group: 'System Actions',
      items: [
        { label: 'Export Current Operational View', action: 'export', icon: Download, shortcut: 'E' },
        { label: 'Toggle Interface Theme', action: 'theme', icon: Eye, shortcut: 'T' },
      ]
    }
  ]

  // Flatten items to compute visual index for staggered animations
  let itemCounter = 0

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput 
        placeholder="Type a command, district, or page search..." 
        value={search}
        onValueChange={setSearch}
      />
      <CommandList className="max-h-[380px] overflow-y-auto py-2 px-1">
        <CommandEmpty>No operational matches found.</CommandEmpty>
        
        {items.map((group, groupIndex) => (
          <div key={group.group}>
            {groupIndex > 0 && <CommandSeparator className="my-1 opacity-40" />}
            <CommandGroup heading={group.group} className="text-muted-foreground">
              {group.items.map((it) => {
                const Icon = it.icon
                const currentIdx = itemCounter++
                return (
                  <CommandItem
                    key={it.label}
                    value={it.label}
                    onSelect={() => handleSelect('to' in it ? it.to : undefined, 'action' in it ? it.action : undefined)}
                    className="flex items-center gap-3 px-3 py-2 rounded-md transition-all duration-75 cursor-pointer data-[selected=true]:bg-accent/10 data-[selected=true]:text-foreground outline-none"
                  >
                    <motion.div
                      className="flex items-center gap-3 w-full"
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ 
                        delay: currentIdx * 0.012, // Exact 12ms stagger reveal
                        type: 'spring',
                        stiffness: 380,
                        damping: 32
                      }}
                    >
                      <Icon className="h-3.5 w-3.5 text-muted-foreground group-data-[selected=true]:text-accent transition-colors" />
                      <span className="flex-1 text-body-sm tracking-tight">{it.label}</span>
                      {'shortcut' in it && it.shortcut && (
                        <kbd className="text-[9px] font-mono text-muted-foreground opacity-80 border border-border/40 px-1 py-0.5 rounded bg-secondary/50">
                          {it.shortcut}
                        </kbd>
                      )}
                    </motion.div>
                  </CommandItem>
                )
              })}
            </CommandGroup>
          </div>
        ))}
      </CommandList>
    </CommandDialog>
  )
}
