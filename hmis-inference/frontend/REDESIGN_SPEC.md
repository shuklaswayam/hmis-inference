# HMIS Intelligence Platform Redesign Specification

## 1. Design Token System

```ts
const tokens = {
  font: {
    sans: '"Inter Variable", "SF Pro Text", -apple-system, sans-serif',
    mono: '"JetBrains Mono Variable", "SF Mono", monospace',
    display: '"Inter Variable", -0.04em tracking, weight 600',
  },
  space: {
    0: '0px',
    2: '2px',
    4: '4px',
    8: '8px',
    12: '12px',
    16: '16px',
    24: '24px',
    32: '32px',
    48: '48px',
    64: '64px',
    96: '96px',
  },
  radius: {
    sm: '6px',
    md: '10px',
    lg: '14px',
    xl: '20px',
    '2xl': '24px',
  },
  elevation: {
    0: 'none',
    1: 'inset 0 1px 0 0 rgba(255, 255, 255, 0.06)',
    2: '0 1px 0 0 rgba(255, 255, 255, 0.04), 0 0 0 1px rgba(255, 255, 255, 0.06)',
  },
  motion: {
    spring: { stiffness: 380, damping: 32, mass: 0.9 },
    snap:   { stiffness: 700, damping: 40, mass: 1 },
    enter:  { duration: 0.18, ease: [0.2, 0.8, 0.2, 1] },
    exit:   { duration: 0.12, ease: [0.4, 0, 1, 1] }
  },
  colors: {
    dark: {
      background: '#0A0A0B',
      card: '#121214',
      border: 'rgba(255, 255, 255, 0.06)',
      accent: '#34D5C2', // Cool Teal
    },
    light: {
      background: '#FAF9F7', // Warm White
      card: '#FFFFFF',
      border: 'rgba(0, 0, 0, 0.06)',
      accent: '#34D5C2',
    }
  }
};
```

---

## 2. ASCII Layout Mockups

### AppShell Layout
```
+---------------------------------------------------------------------------------+
|   ||  Breadcrumbs > Current Page                     [Search / Cmd+K]  (Actions) | (TopBar 48px)
+===++============================================================================+
| S ||                                                                            |
| i ||                                                                            |
| d ||                                                                            |
| e ||                                                                            |
| b ||                               Center Canvas (Main)                         |
| a ||                                                                            |
| r ||                                                                            |
|   ||                                                                            |
|   ||                                                                            |
+---+-----------------------------------------------------------------------------+
```

### OverviewPage
```
+---------------------------------------------------------------------------------+
| AI Ribbon: "OPD volume in Ahmedabad North is 23% above 7-day baseline"   (Dismiss) |
+---------------------------------------------------------------------------------+
| +------------------------------------+ +------------------+ +------------------+ |
| | HERO KPI: ICU Capacity             | | OPD Volume       | | Outbreak Signals | |
| | 84% occupied (+4.2%)               | | 12,402           | | 3 Active         | |
| +------------------------------------+ +------------------+ +------------------+ |
+---------------------------------------------------------------------------------+
| +------------------------------------------+ +--------------------------------+ |
| |                                          | | Selection Panel Detail         | |
| |              Gujarat Map                 | |                                | |
| |             (Choropleth)                 | | Outbreak detected in:          | |
| |                                          | | Surat District                 | |
| |                                          | | - Actionable insight items     | |
| +------------------------------------------+ +--------------------------------+ |
+---------------------------------------------------------------------------------+
| Live Alert Feed (No Clutter, 1-line rows with spring expand click)              |
+---------------------------------------------------------------------------------+
```

### AIPage
```
+---------------------+-----------------------------------------------------------+
| Model Selection     | Chat Workspace (No ChatGPT Clone. Focused, clean layout)  |
| - Model ID          |                                                           |
| - Temperature       | Prompt Input (Cmd+Enter to execute)                       |
| - Tokens            | Citations chips that expand to footer inspector scroll    |
+---------------------+-----------------------------------------------------------+
```

### AlertsPage
```
+---------------------------------------------------------------------------------+
| [ All Alerts ] [ Critical ] [ High ] [ Acknowledged ]                           |
+---------------------------------------------------------------------------------+
| Gutter | Target / Alert Source               | Severity | Time     | Status     |
| [Glyph]| ICU occupancy critical Ahmedabad    | Critical | 10m ago  | Unread     |
| [Glyph]| Typhoid spike in Mehsana            | Warning  | 1h ago   | Ack        |
+---------------------------------------------------------------------------------+
| Bulk Actions (Contextual slide-up bottom toolbar when rows selected)            |
+---------------------------------------------------------------------------------+
```

### InvestigationsPage
```
+---------------------------------------------------------------------------------+
| Timeline Hybrid (Drag and Drop Nodes)                                           |
| [ Day 1 ] --------> [ Day 2 ] --------> [ Day 3 ] --------> [ Day 4 ]            |
|   |                   |                                                          |
|   v                   v                                                          |
| Node A              Node B                                                       |
+---------------------------------------------------------------------------------+
```

### AnalyticsPage
```
+---------------------------------------------------------------------------------+
| Recharts Custom Minimalist (No default chart grid junk)                         |
| numbers in JetBrains Mono font                                                  |
+---------------------------------------------------------------------------------+
```

### ReportsPage
```
+---------------------------------------------------------------------------------+
| Generated Reports (Quiet rows, 24px tall, Action: Open)                          |
+---------------------------------------------------------------------------------+
```

### FacilitiesPage
```
+---------------------------------------------------------------------------------+
| Table: Sticky headers, Monospaced figures, Zebra stripe via opacity 0.03        |
+---------------------------------------------------------------------------------+
```

### SettingsPage
```
+---------------------------------------------------------------------------------+
| Header Content                                                                  |
| ------------------------------------------------------------------------------- |
| Section 1 Inputs/Controls                                                       |
+---------------------------------------------------------------------------------+
```

---

## 3. Signature Motion Moments
1. **Command Palette Entry**: Pop-in scale spring (0.98 -> 1.0) with stagger-revealed options (12ms increments).
2. **Sidebar Expand/Collapse**: Smooth spring physics width transition.
3. **Alert Feed Detail Reveal**: Spring accordion expansion on click.

---

## 4. Accessibility Verification Matrix
- **Color Contrast**: 4.5:1 minimum for regular text, 7:1 for bold/essential labels.
- **Focus Rings**: `focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2`
- **ARIA/Semantic**: Dynamic active state announcement with `aria-live`.
- **Keyboard Shortcuts**: `⌘K` triggers global command menu, `Escape` exits.

---

## 5. Phased Implementation Order
1. **Phase 1**: Base Design System (tokens, tailwind, root css variables).
2. **Phase 2**: Global Layout (AppShell, Sidebar, TopBar).
3. **Phase 3**: Global Command Palette.
4. **Phase 4**: Overview Dashboard Page.
5. **Phase 5**: Sub-pages Refactoring.
