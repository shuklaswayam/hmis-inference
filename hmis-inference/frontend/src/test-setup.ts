// Vitest global setup — import jest-dom matchers once for the whole suite.
import '@testing-library/jest-dom/vitest'

// jsdom doesn't implement matchMedia. AppShell uses it for theme-related
// layout shifts; stub it so component renders don't blow up.
if (typeof window !== 'undefined' && !window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  })
}

// Pointer events aren't in jsdom by default — Radix components rely on them.
if (typeof window !== 'undefined' && !(window as any).PointerEvent) {
  class PointerEventStub extends Event {
    constructor(type: string, params: EventInit = {}) {
      super(type, params)
    }
  }
  ;(window as any).PointerEvent = PointerEventStub
}
