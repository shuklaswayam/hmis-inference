import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth, type AuthUser } from '@/auth/AuthContext'

export default function LoginPage() {
  return (
    <main
      role="main"
      className="flex min-h-screen items-center justify-center bg-background text-foreground"
    >
      <CardScaffold>
        <LoginForm />
        <Hint />
     </CardScaffold>
   </main>
  )
}

function LoginForm() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setErr(null)
    try {
      await login(email.trim(), password)
      navigate('/', { replace: true })
    } catch (e: any) {
      setErr(e?.message ?? 'login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      onSubmit={submit}
      aria-label="Sign in"
      className="space-y-3 max-w-sm w-full"
    >
      <fieldset className="space-y-3" disabled={busy}>
        <legend className="text-[10px] tracking-widest uppercase font-semibold text-muted-foreground">
          Sign in
       </legend>
        <label className="block text-[12px] text-foreground">
          <span className="block text-muted-foreground mb-1">Email</span>
          <input
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full h-9 px-3 rounded-md border border-border bg-card text-[13px] outline-none focus:border-accent"
          />
       </label>
        <label className="block text-[12px] text-foreground">
          <span className="block text-muted-foreground mb-1">Password</span>
          <input
            type="password"
            autoComplete="current-password"
            required
            minLength={4}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full h-9 px-3 rounded-md border border-border bg-card text-[13px] outline-none focus:border-accent"
          />
       </label>
        <button
          type="submit"
          className="w-full h-9 rounded-md bg-accent text-background font-semibold text-[13px] hover:opacity-90 disabled:opacity-50"
          disabled={busy}
        >
          {busy ? 'Signing in…' : 'Sign in'}
       </button>
        {err ? (
          <p role="alert" className="text-destructive text-[12px]">
            {err}
         </p>
        ) : null}
     </fieldset>
   </form>
  )
}


function CardScaffold({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border/80 bg-card/80 backdrop-blur-md p-6 max-w-sm w-full space-y-4 shadow-lg">
      <div className="space-y-1">
        <h1 className="text-heading-lg font-bold tracking-tight">Artem</h1>
        <p className="text-body-sm text-muted-foreground">
          Gujarat HMIS Intelligence platform.
       </p>
     </div>
      {children}
   </div>
  )
}

function Hint() {
  return (
    <p className="text-caption text-muted-foreground">
      Tip: bootstrap the first COMMISSIONER with{' '}
      <code className="font-mono text-accent">python scripts/create_commissioner.py</code>
      .
   </p>
  )
}

// Re-export for tests / external bootstrap.
export { useAuth, type AuthUser }
