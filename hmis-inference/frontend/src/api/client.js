import axios from 'axios'

// Read the backend's base URL from the Vite env at build time.
// Override by setting VITE_API_BASE_URL in frontend/.env (see frontend/.env.example).
// Trailing slashes are stripped so paths like '/api/v1/foo' concatenate cleanly.
const rawBase = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').trim()
const baseURL = rawBase.replace(/\/+$/, '')

// Optional legacy API_KEY — kept for service-to-service compatibility
// when the operator hasn't yet migrated to JWT.
const apiKey = (import.meta.env.VITE_API_KEY || '').trim()

const client = axios.create({
  baseURL,
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json',
    ...(apiKey && { 'X-API-Key': apiKey }),
  },
})

// Phase-4 JWT support: pull the access token from localStorage at
// request time so the SPA doesn't have to wrap every axios call in a
// React Context lookup. The AuthContext persists the token to
// localStorage on every login/refresh/logout.
client.interceptors.request.use((config) => {
  try {
    const tok = typeof window !== 'undefined'
      ? window.localStorage.getItem('hmis:auth:access')
      : null
    if (tok) {
      config.headers = config.headers ?? {}
      config.headers.Authorization = `Bearer ${tok}`
    }
  } catch (_) {
    // localStorage may not be available (SSR / test); ignore.
  }
  return config
})

export default client
