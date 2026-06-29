import { useEffect, useRef, useState } from 'react'

export interface RealtimeMessage {
  /** server-emitted event name: 'message', 'heartbeat' etc. */
  event: string
  /** raw JSON payload as text */
  data: string
  /** Parsed JSON when available */
  parsed?: unknown
}

export interface RealtimeConnection {
  status: 'connecting' | 'open' | 'closed'
  lastMessageAt: number | null
}

/**
 * Subscribe to the /api/v1/realtime/events SSE stream.
 *
 * Returns the most-recent message + connection status. Components that
 * care about specific workstreams can hook into this hook to trigger
 * refetches (the cache_warmed event, CRITICAL transitions, etc.).
 */
export function useRealtimeStream(): {
  status: RealtimeConnection['status']
  lastMessage: RealtimeMessage | null
} {
  const [status, setStatus] = useState<RealtimeConnection['status']>('connecting')
  const [lastMessage, setLastMessage] = useState<RealtimeMessage | null>(null)
  const ref = useRef<EventSource | null>(null)

  useEffect(() => {
    if (typeof window === 'undefined') return
    setStatus('connecting')
    const es = new EventSource('/api/v1/realtime/events')
    ref.current = es

    es.onopen = () => setStatus('open')
    es.onerror = () => setStatus('closed')
    es.onmessage = (ev: MessageEvent) => {
      let parsed: unknown
      try { parsed = JSON.parse(ev.data) } catch { /* heartbeat */ }
      setLastMessage({ event: 'message', data: ev.data, parsed })
    }
    es.addEventListener('heartbeat', () => {
      setStatus('open')
    })

    return () => {
      es.close()
      ref.current = null
    }
  }, [])

  return { status, lastMessage }
}
