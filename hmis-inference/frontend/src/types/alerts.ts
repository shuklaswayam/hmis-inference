// Single source of truth for API-shaped types referenced by both pages and
// components. Kept in its own module so we don't get import cycles between
// page-level consumers and the deeper component tree.

export interface Alert {
  id: number | string
  district_id?: number | string
  severity?: string
  [key: string]: unknown
}
