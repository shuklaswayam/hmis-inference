import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-caption font-medium transition-colors focus:outline-none",
  {
    variants: {
      variant: {
        default: "bg-secondary text-secondary-foreground",
        primary: "bg-primary text-primary-foreground",
        accent: "bg-accent/10 text-accent border border-accent/20",
        secondary: "bg-secondary text-secondary-foreground border border-border/40",
        outline: "border border-border text-foreground bg-transparent",
        muted: "bg-muted text-muted-foreground",
        // Severity — semantic for alerts
        critical: "bg-severity-critical/10 text-severity-critical border border-severity-critical/20",
        high: "bg-severity-high/10 text-severity-high border border-severity-high/20",
        medium: "bg-severity-medium/10 text-severity-medium border border-severity-medium/20",
        low: "bg-severity-low/10 text-severity-low border border-severity-low/20",
        // Status — used for connection / state indicators
        success: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30",
        warning: "bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30",
      },
      size: {
        sm: "text-[10px] px-1.5 py-0",
        default: "text-caption",
        lg: "text-body-sm px-2 py-0.5",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, size, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant, size, className }))} {...props} />
  )
}

export { Badge, badgeVariants }
