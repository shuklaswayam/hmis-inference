import animate from 'tailwindcss-animate'

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    container: {
      center: true,
      padding: '1.5rem',
      screens: { '2xl': '1440px' },
    },
    extend: {
      colors: {
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))',
        },
        success: {
          DEFAULT: 'hsl(var(--success))',
          foreground: 'hsl(var(--success-foreground))',
        },
        warning: {
          DEFAULT: 'hsl(var(--warning))',
          foreground: 'hsl(var(--warning-foreground))',
        },
        info: {
          DEFAULT: 'hsl(var(--info))',
          foreground: 'hsl(var(--info-foreground))',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))',
        },
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))',
        },
        severity: {
          critical: 'hsl(var(--severity-critical))',
          high: 'hsl(var(--severity-high))',
          medium: 'hsl(var(--severity-medium))',
          low: 'hsl(var(--severity-low))',
          info: 'hsl(var(--severity-info))',
        },
        sidebar: {
          DEFAULT: 'hsl(var(--sidebar))',
          foreground: 'hsl(var(--sidebar-foreground))',
          muted: 'hsl(var(--sidebar-muted))',
          accent: 'hsl(var(--sidebar-accent))',
          border: 'hsl(var(--sidebar-border))',
        },
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      fontSize: {
        // Display — page hero numerals (KPI block)
        'display-2xl': ['4.5rem', { lineHeight: '1', letterSpacing: '-0.04em', fontWeight: '600' }],
        'display-xl': ['3.5rem', { lineHeight: '1.05', letterSpacing: '-0.035em', fontWeight: '600' }],
        'display-lg': ['2.75rem', { lineHeight: '1.1', letterSpacing: '-0.03em', fontWeight: '600' }],
        // Headings
        'heading-lg': ['1.875rem', { lineHeight: '1.2', letterSpacing: '-0.02em', fontWeight: '600' }],
        'heading-md': ['1.5rem', { lineHeight: '1.3', letterSpacing: '-0.015em', fontWeight: '600' }],
        'heading-sm': ['1.25rem', { lineHeight: '1.4', letterSpacing: '-0.01em', fontWeight: '600' }],
        // Subheading
        'subheading': ['1rem', { lineHeight: '1.5', letterSpacing: '-0.005em', fontWeight: '500' }],
        // Body
        'body-lg': ['0.9375rem', { lineHeight: '1.5', fontWeight: '400' }],
        'body': ['0.875rem', { lineHeight: '1.5', fontWeight: '400' }],
        'body-sm': ['0.8125rem', { lineHeight: '1.45', fontWeight: '400' }],
        // Caption / label
        'caption': ['0.75rem', { lineHeight: '1.4', fontWeight: '500', letterSpacing: '0.01em' }],
        'overline': ['0.6875rem', { lineHeight: '1.3', fontWeight: '600', letterSpacing: '0.08em', textTransform: 'uppercase' as const }],
      },
      spacing: {
        '4xs': '0.125rem', // 2
        '3xs': '0.25rem',  // 4
        '2xs': '0.5rem',   // 8
        'xs': '0.75rem',   // 12
        'sm': '1rem',      // 16
        'md': '1.5rem',    // 24
        'lg': '2rem',      // 32
        'xl': '3rem',      // 48
        '2xl': '4rem',     // 64
        '3xl': '6rem',     // 96
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in-left': {
          from: { opacity: '0', transform: 'translateX(-6px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
        'slide-up': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'pulse-dot': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
        'skeleton-pulse': {
          '0%': { backgroundColor: 'hsl(var(--muted))' },
          '50%': { backgroundColor: 'hsl(var(--muted) / 0.7)' },
          '100%': { backgroundColor: 'hsl(var(--muted))' },
        },
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
      },
      animation: {
        'fade-in': 'fade-in 200ms ease-out',
        'slide-in-left': 'slide-in-left 180ms ease-out',
        'slide-up': 'slide-up 220ms ease-out',
        'pulse-dot': 'pulse-dot 2s ease-in-out infinite',
        'skeleton-pulse': 'skeleton-pulse 1.5s ease-in-out infinite',
        'accordion-down': 'accordion-down 200ms ease-out',
        'accordion-up': 'accordion-up 200ms ease-out',
      },
      boxShadow: {
        'soft-sm': '0 1px 2px 0 hsl(var(--foreground) / 0.04)',
        'soft': '0 1px 3px 0 hsl(var(--foreground) / 0.06), 0 1px 2px -1px hsl(var(--foreground) / 0.06)',
        'soft-md': '0 4px 8px -2px hsl(var(--foreground) / 0.06), 0 2px 4px -2px hsl(var(--foreground) / 0.04)',
        'soft-lg': '0 12px 24px -6px hsl(var(--foreground) / 0.08), 0 4px 8px -4px hsl(var(--foreground) / 0.04)',
        'soft-xl': '0 24px 48px -12px hsl(var(--foreground) / 0.12), 0 8px 16px -6px hsl(var(--foreground) / 0.06)',
        'focus-ring': '0 0 0 3px hsl(var(--ring) / 0.15)',
      },
    },
  },
  plugins: [animate],
}
