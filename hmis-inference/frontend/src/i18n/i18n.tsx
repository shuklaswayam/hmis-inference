import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

// Eager import — the JSONs are small and we always want them in the bundle.
import en from './en.json'
import hi from './hi.json'
import gu from './gu.json'

export type Locale = 'en' | 'hi' | 'gu'

const STORAGE_KEY = 'hmis:locale'

const dictionaries: Record<Locale, Record<string, string>> = {
  en,
  hi,
  gu,
}

export const SUPPORTED_LOCALES: { code: Locale; label: string }[] = [
  { code: 'en', label: 'EN'  },
  { code: 'hi', label: 'HI'  },
  { code: 'gu', label: 'ગુ'  },
]

interface I18nState {
  locale: Locale
  setLocale: (l: Locale) => void
  t: (key: string) => string
}

const I18nContext = createContext<I18nState | undefined>(undefined)

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocale] = useState<Locale>(() => {
    if (typeof window === 'undefined') return 'en'
    return (window.localStorage.getItem(STORAGE_KEY) as Locale) || 'en'
  })

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(STORAGE_KEY, locale)
  }, [locale])

  const t = useCallback((key: string) => {
    const dict = dictionaries[locale] ?? dictionaries.en
    if (key in dict) return dict[key]
    // Fallback to en, then key itself if missing.
    if (key in dictionaries.en) return dictionaries.en[key]
    return key
  }, [locale])

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, t])
  return (
    <I18nContext.Provider value={value}>
      {children}
   </I18nContext.Provider>
  )
}

export function useI18n(): I18nState {
  const ctx = useContext(I18nContext)
  if (!ctx) return fallback()
  return ctx
}

/** Fallback when no provider is mounted (e.g. SSR/test) — leaves t as no-op. */
function fallback(): I18nState {
  const t = (k: string) => dictionaries.en[k] ?? k
  return { locale: 'en', setLocale: () => undefined, t }
}
