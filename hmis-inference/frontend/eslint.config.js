import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  // Tooling config files use Node-only globals (e.g. __dirname) and Tailwind's
  // `as const` — the browser-only ESLint preset can't parse either. Lint them
  // separately if/when needed.
  globalIgnores([
    'dist',
    'tailwind.config.js',
    'vite.config.js',
    'postcss.config.js',
    'eslint.config.js',
  ]),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
  },
])
