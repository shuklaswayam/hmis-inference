import { describe, it, expect } from 'vitest'
import { cn } from '../utils'

describe('cn', () => {
  it('joins truthy class names with spaces', () => {
    expect(cn('a', 'b', 'c')).toBe('a b c')
  })

  it('drops falsy values', () => {
    expect(cn('a', undefined, null, false, 0, '', 'b')).toBe('a b')
  })

  it('handles arrays and objects (clsx behaviour)', () => {
    expect(cn(['a', 'b'], { c: true, d: false })).toBe('a b c')
  })

  it('dedupes conflicting tailwind utilities (tailwind-merge behaviour)', () => {
    // tailwind-merge keeps the last conflicting class.
    expect(cn('p-2', 'p-4')).toBe('p-4')
    expect(cn('text-red-500', 'text-blue-500')).toBe('text-blue-500')
  })

  it('preserves non-conflicting classes alongside conflicting ones', () => {
    // text-* and bg-* never conflict with p-* / m-*. Merging them should
    // leave every one intact.
    expect(cn('text-red-500', 'bg-blue-500', 'p-4', 'p-2')).toBe('text-red-500 bg-blue-500 p-2')
  })

  it('returns a string for any input (does not throw)', () => {
    expect(typeof cn('px-2 py-2', 'p-4')).toBe('string')
    expect(typeof cn()).toBe('string')
    expect(typeof cn(null, undefined)).toBe('string')
  })
})
