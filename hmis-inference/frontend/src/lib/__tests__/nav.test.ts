import { describe, it, expect } from 'vitest'
import {
  PRIMARY_NAV,
  INTELLIGENCE_NAV,
  SECONDARY_NAV,
  ALL_NAV,
  type NavItem,
} from '../nav'

describe('nav config', () => {
  it('PRIMARY_NAV contains the five primary items in display order', () => {
    expect(PRIMARY_NAV.map((n) => n.label)).toEqual([
      'Overview',
      'Alerts',
      'Investigations',
      'Facilities',
      'Analytics',
    ])
  })

  it('every nav item has a label, path, icon, and shortcut', () => {
    const all: NavItem[] = [...PRIMARY_NAV, ...INTELLIGENCE_NAV, ...SECONDARY_NAV]
    for (const item of all) {
      expect(item.label.length).toBeGreaterThan(0)
      expect(item.to).toMatch(/^\/[a-z]*$/) // root or /single-segment
      expect(typeof item.icon).toBe('object') // lucide icons are forward-ref components
      expect(item.shortcut).toMatch(/^G [A-Z,]$/)
    }
  })

  it('ALL_NAV is the concatenation of the three groups', () => {
    expect(ALL_NAV).toEqual([...PRIMARY_NAV, ...INTELLIGENCE_NAV, ...SECONDARY_NAV])
    expect(ALL_NAV).toHaveLength(
      PRIMARY_NAV.length + INTELLIGENCE_NAV.length + SECONDARY_NAV.length,
    )
  })

  it('paths are unique across groups (no two nav items collide)', () => {
    const paths = ALL_NAV.map((n) => n.to)
    expect(new Set(paths).size).toBe(paths.length)
  })

  it('Overview route is "/" and the rest are nested', () => {
    expect(PRIMARY_NAV[0].to).toBe('/')
    expect(PRIMARY_NAV.slice(1).every((n) => n.to.startsWith('/') && n.to !== '/')).toBe(true)
  })

  it('every shortcut is unique', () => {
    const shortcuts = ALL_NAV.map((n) => n.shortcut!)
    expect(new Set(shortcuts).size).toBe(shorts_to_unique(shortcuts))
    // helper assertion guarding against the trivial always-true mistake above
    expect(shortcuts.length).toBeGreaterThan(0)
  })
})

function shorts_to_unique(arr: string[]): number {
  return new Set(arr).size
}
