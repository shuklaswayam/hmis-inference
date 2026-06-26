export const tokens = {
  font: {
    sans: '"Inter Variable", "Inter", "SF Pro Text", -apple-system, sans-serif',
    mono: '"JetBrains Mono Variable", "JetBrains Mono", "SF Mono", monospace',
    display: '"Inter Variable", "Inter", sans-serif',
  },
  // 8pt grid, with 4pt for micro spacing
  space: {
    0: '0px',
    '4xs': '2px',
    '3xs': '4px',
    '2xs': '8px',
    xs: '12px',
    sm: '16px',
    md: '24px',
    lg: '32px',
    xl: '48px',
    '2xl': '64px',
    '3xl': '96px',
  },
  radius: {
    sm: '6px',
    md: '10px',
    lg: '14px',
    xl: '20px',
    '2xl': '24px',
  },
  elevation: {
    none: 'none',
    1: 'inset 0 1px 0 0 rgba(255, 255, 255, 0.06)',
    2: '0 1px 0 0 rgba(255, 255, 255, 0.04), 0 0 0 1px rgba(255, 255, 255, 0.06)',
  },
  motion: {
    spring: {
      type: 'spring',
      stiffness: 380,
      damping: 32,
      mass: 0.9,
    },
    snap: {
      type: 'spring',
      stiffness: 700,
      damping: 40,
      mass: 1,
    },
    enter: {
      duration: 0.18,
      ease: [0.2, 0.8, 0.2, 1],
    },
    exit: {
      duration: 0.12,
      ease: [0.4, 0, 1, 1],
    },
  },
} as const;
