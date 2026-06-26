import { type ReactNode } from 'react'
import { LayoutDashboard, type LucideIcon } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

interface PageHeaderProps {
  icon?: LucideIcon
  eyebrow?: string
  title: string
  description?: string
  actions?: ReactNode
  className?: string
}

export function PageHeader({
  icon: Icon,
  eyebrow,
  title,
  description,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <div className={cn('flex items-start justify-between gap-6 mb-6', className)}>
      <div className="min-w-0">
        {eyebrow && (
          <div className="flex items-center gap-2 text-overline text-muted-foreground mb-2">
            {Icon && <Icon className="h-3 w-3" />}
            {eyebrow}
        </div>
        )}
        <h1 className="text-heading-lg font-semibold tracking-tight text-foreground leading-tight">
          {title}
      </h1>
        {description && (
          <p className="text-body text-muted-foreground mt-1.5 max-w-prose">
            {description}
        </p>
        )}
    </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
  </div>
  )
}

interface PagePlaceholderProps {
  title: string
  description: string
  phase: string
  icon: LucideIcon
}

export function PagePlaceholder({ title, description, phase, icon: Icon }: PagePlaceholderProps) {
  return (
    <section className="animate-fade-in">
      <PageHeader
        icon={LayoutDashboard}
        eyebrow="HMIS Intelligence"
        title={title}
        description={description}
        actions={
          <Badge variant="accent" size="sm">
            {phase}
        </Badge>
        }
      />
      <div className="rounded-lg border border-dashed border-border bg-card/40 p-12 text-center">
        <div className="mx-auto h-10 w-10 rounded-md bg-secondary grid place-items-center mb-3">
          <Icon className="h-5 w-5 text-muted-foreground" />
      </div>
        <p className="text-body-sm text-muted-foreground max-w-md mx-auto">
          This surface is reserved for milestone 2. The design system, navigation, and shell
          are in place — content lands after the foundation review.
      </p>
        <Button variant="outline" size="sm" className="mt-4">
          Read milestone plan
      </Button>
    </div>
  </section>
  )
}
