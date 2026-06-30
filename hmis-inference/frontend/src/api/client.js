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
  } catch {
    // localStorage may not be available (SSR / test); ignore.
  }
  return config
})

// Self-healing on 401: if the request carried a stored token that
// the backend has rejected (TTL expired / signature rotated / logout-
// blacklisted), drop the local auth state and signal AuthContext via
// a window event so the router can bounce the user to /login. The
// `hadToken` guard prevents an infinite clear-and-retry loop after
// the user is already signed out (no token → no event).
client.interceptors.response.use(undefined, (error) => {
  const status = error?.response?.status
  if (status !== 401) return Promise.reject(error)
  if (typeof window === 'undefined') return Promise.reject(error)
  try {
    const hadToken = !!window.localStorage.getItem('hmis:auth:access')
    if (!hadToken) return Promise.reject(error)
    window.localStorage.removeItem('hmis:auth:access')
    window.localStorage.removeItem('hmis:auth:refresh')
    window.localStorage.removeItem('hmis:auth:user')
    window.dispatchEvent(new CustomEvent('hmis:auth:expired'))
  } catch {
    // ignore — the worst case is the user sees the original error
  }
  return Promise.reject(error)
})

export default client
