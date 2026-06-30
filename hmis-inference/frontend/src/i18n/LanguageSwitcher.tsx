import { useI18n, SUPPORTED_LOCALES, type Locale } from '@/i18n'

/**
 * Header-mounted dropdown that lets the operator pick the dashboard
 * language. Persists the choice in localStorage via I18nProvider.
 */
export function LanguageSwitcher() {
  const { locale, setLocale } = useI18n()
  return (
    <label
      className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-muted-foreground"
      aria-label="Language switcher"
    >
      <span className="sr-only">Language</span>
      <select
        value={locale}
        onChange={(e) => setLocale(e.target.value as Locale)}
        className="h-6 px-1.5 rounded border border-border/60 bg-secondary/30 text-foreground text-[10px] tracking-wider focus:outline-none focus:border-accent"
      >
        {SUPPORTED_LOCALES.map((l) => (
          <option key={l.code} value={l.code}>{l.label}</option>
        ))}
     </select>
   </label>
  )
}
