import { createContext, useCallback, useContext, useEffect, useState } from 'react'

export interface AuthUser {
  id: string
  email: string
  full_name: string
  role: 'COMMISSIONER' | 'STATE_OFFICER' | 'DISTRICT_OFFICER' | 'FACILITY_HEAD' | 'VIEWER'
  district_id?: string | null
  facility_id?: string | null
}

interface AuthState {
  user: AuthUser | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthState | undefined>(undefined)

const LS_ACCESS = 'hmis:auth:access'
const LS_REFRESH = 'hmis:auth:refresh'
const LS_USER = 'hmis:auth:user'

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => {
    if (typeof window === 'undefined') return null
    try {
      const raw = window.localStorage.getItem(LS_USER)
      return raw ? JSON.parse(raw) : null
    } catch { return null }
  })
  const [accessToken, setAccess] = useState<string | null>(() =>
    typeof window !== 'undefined' ? window.localStorage.getItem(LS_ACCESS) : null,
  )
  const [refreshToken, setRefresh] = useState<string | null>(() =>
    typeof window !== 'undefined' ? window.localStorage.getItem(LS_REFRESH) : null,
  )

  // Persist.
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (user) window.localStorage.setItem(LS_USER, JSON.stringify(user))
    else window.localStorage.removeItem(LS_USER)
  }, [user])
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (accessToken) window.localStorage.setItem(LS_ACCESS, accessToken)
    else window.localStorage.removeItem(LS_ACCESS)
  }, [accessToken])
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (refreshToken) window.localStorage.setItem(LS_REFRESH, refreshToken)
    else window.localStorage.removeItem(LS_REFRESH)
  }, [refreshToken])

  // Self-healing: the axios client in api/client.js dispatches a
  // 'hmis:auth:expired' window event whenever it sees a 401 with a
  // token attached. Drop in-memory state here so ProtectedShell
  // bounces the user to /login instead of rendering an empty
  // dashboard over an invalid session.
  useEffect(() => {
    if (typeof window === 'undefined') return
    const handler = () => {
      setUser(null)
      setAccess(null)
      setRefresh(null)
    }
    window.addEventListener('hmis:auth:expired', handler)
    return () => window.removeEventListener('hmis:auth:expired', handler)
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const baseURL = (import.meta as any).env?.VITE_API_BASE_URL ?? ''
    const res = await fetch(`${baseURL}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ email, password }),
    })
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}))
      throw new Error(detail.detail ?? `login failed (${res.status})`)
    }
    const body = await res.json() as {
      access_token: string
      refresh_token: string
      user: AuthUser
    }
    setAccess(body.access_token)
    setRefresh(body.refresh_token)
    setUser(body.user)
  }, [])

  const logout = useCallback(() => {
    setUser(null)
    setAccess(null)
    setRefresh(null)
  }, [])

  const refresh = useCallback(async () => {
    if (!refreshToken) return
    const baseURL = (import.meta as any).env?.VITE_API_BASE_URL ?? ''
    const res = await fetch(`${baseURL}/api/v1/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    if (!res.ok) return
    const body = await res.json() as { access_token: string; refresh_token: string; user: AuthUser }
    setAccess(body.access_token)
    setRefresh(body.refresh_token)
    setUser(body.user)
  }, [refreshToken])

  return (
    <AuthContext.Provider
      value={{
        user,
        accessToken,
        refreshToken,
        isAuthenticated: !!user && !!accessToken,
        login,
        logout,
        refresh,
      }}
    >
      {children}
   </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
