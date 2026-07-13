import { useQuery, useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { Sparkles, Send, Loader2, AlertTriangle, FileText, ExternalLink } from 'lucide-react'

import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import client from '@/api/client'

type Confidence = 'low' | 'medium' | 'high'
//sss
interface AskResponse {
  question: string
  answer: string
  sources: string[]
  district_id: string | null
  timestamp: string
  // Structured analysis sections from the backend. May be empty for
  // structured-data queries or for refusal fallback responses.
  what_is_happening?: string
  why_it_happening?: string
  recommended_action?: string
  confidence?: Confidence
  intent?: string
  refused?: boolean
}

interface Alert {
  id: string
  severity: string
  facility_name: string
  district_name: string
  what_is_happening: string
  confidence_score: number
  llm_generated: boolean
  created_at: string
}

const CONFIDENCE_BADGE: Record<Confidence, { label: string; className: string }> = {
  high: { label: 'High confidence', className: 'bg-success/10 text-success border-success/30' },
  medium: { label: 'Medium confidence', className: 'bg-warning/10 text-warning border-warning/30' },
  low: { label: 'Low confidence', className: 'bg-severity-critical/10 text-severity-critical border-severity-critical/30' },
}

const INTENT_LABEL: Record<string, string> = {
  policy_llm: 'Policy LLM',
  structured_list_facilities: 'Facility list',
  structured_capacity_summary: 'Capacity summary',
  structured_no_match: 'No match',
}

export default function AIPage() {
  const [query, setQuery] = useState('')
  const [chatHistory, setChatHistory] = useState<AskResponse[]>([])

  const askMutation = useMutation({
    mutationFn: async (q: string) => {
      const res = await client.post('/api/v1/ask', { query: q })
      return res.data as AskResponse
    },
    onSuccess: (data) => {
      setChatHistory((prev) => [...prev, data])
      setQuery('')
    },
  })

  const recentAlertsQuery = useQuery<Alert[]>({
    queryKey: ['alerts', 'ai-recent'],
    queryFn: async ({ signal }) => {
      const res = await client.get('/api/v1/alerts/', { params: { severity: 'HIGH' }, signal })
      return (res.data ?? []) as Alert[]
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim() || askMutation.isPending) return
    askMutation.mutate(query.trim())
  }

  const suggestedQuestions = [
    'What are the main disease trends in Ahmedabad district?',
    'Which facilities have the highest ICU occupancy?',
    'What policy changes could reduce maternal mortality?',
    'Summarize the current alert situation across all districts.',
  ]

  return (
    <section className="animate-fade-in">
      <PageHeader
        eyebrow="Intelligence"
        title="AI Intelligence"
        description="Briefings, confidence distributions, and ingestion of recent model decisions."
        actions={
          <Badge variant="accent" size="sm">
            <Sparkles className="h-3 w-3 mr-1" />
            Artem AI
          </Badge>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_340px] min-h-[600px]">
        <Card className="overflow-hidden border-border/80 flex flex-col">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-border/60">
            <Sparkles className="h-4 w-4 text-accent" />
            <h2 className="text-heading-sm font-semibold tracking-tight">Ask Artem</h2>
            <span className="text-caption text-muted-foreground">Policy-aware Q&A</span>
          </div>

          <ScrollArea className="flex-1 h-[460px]">
            <div className="p-4 space-y-4">
              {chatHistory.length === 0 && !askMutation.isPending && (
                <div className="py-8 text-center">
                  <Sparkles className="h-10 w-10 text-accent/30 mx-auto mb-4" />
                  <h3 className="text-subheading font-semibold text-foreground mb-2">Ask anything about health data</h3>
                  <p className="text-body-sm text-muted-foreground max-w-md mx-auto mb-6">
                    Artem uses policy documents, district metrics, and alert data to provide informed answers.
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-lg mx-auto">
                    {suggestedQuestions.map((sq) => (
                      <button
                        key={sq}
                        onClick={() => { setQuery(sq); askMutation.mutate(sq) }}
                        className="text-left text-caption text-muted-foreground hover:text-foreground p-2.5 rounded-md border border-border/60 hover:border-accent/30 hover:bg-accent/5 transition-colors"
                      >
                        {sq}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {chatHistory.map((msg, i) => {
                const structured = msg.what_is_happening || msg.why_it_happening || msg.recommended_action
                return (
                  <div key={i} className="space-y-3 animate-fade-in">
                    {/* User question */}
                    <div className="flex justify-end">
                      <div className="bg-accent/10 text-foreground rounded-lg px-4 py-2.5 max-w-[80%] text-body">
                        {msg.question}
                      </div>
                    </div>
                    {/* AI answer */}
                    <div className="flex gap-3">
                      <div className="h-7 w-7 rounded-md bg-accent/10 grid place-items-center shrink-0 mt-0.5">
                        <Sparkles className="h-3.5 w-3.5 text-accent" />
                      </div>
                      <div className="bg-secondary/60 rounded-lg px-4 py-3 max-w-[85%] space-y-3">
                        {structured ? (
                          <div className="space-y-3">
                            {msg.what_is_happening && (
                              <p className="text-body text-foreground/90 leading-relaxed whitespace-pre-wrap">
                                {msg.what_is_happening}
                              </p>
                            )}
                            {msg.why_it_happening && (
                              <div className="border-l-2 border-border/60 pl-3 space-y-1">
                                <p className="text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
                                  Why
                                </p>
                                <p className="text-body-sm text-foreground/85 leading-relaxed whitespace-pre-wrap">
                                  {msg.why_it_happening}
                                </p>
                              </div>
                            )}
                            {msg.recommended_action && (
                              <div className="border-l-2 border-accent/60 pl-3 space-y-1">
                                <p className="text-[10.5px] font-semibold uppercase tracking-wider text-accent">
                                  Recommended action
                                </p>
                                <p className="text-body-sm text-foreground/85 leading-relaxed whitespace-pre-wrap">
                                  {msg.recommended_action}
                                </p>
                              </div>
                            )}
                          </div>
                        ) : (
                          <p className="text-body text-foreground/90 leading-relaxed whitespace-pre-wrap">
                            {msg.answer || 'No response generated.'}
                          </p>
                        )}

                        {/* Footer: status row (intent, confidence, refused) */}
                        {(msg.intent || msg.confidence || msg.refused) && (
                          <div className="flex flex-wrap items-center gap-1.5 pt-2 border-t border-border/40">
                            {msg.intent && INTENT_LABEL[msg.intent] && (
                              <Badge variant="secondary" size="sm">{INTENT_LABEL[msg.intent]}</Badge>
                            )}
                            {msg.confidence && (
                              <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${CONFIDENCE_BADGE[msg.confidence].className}`}>
                                {CONFIDENCE_BADGE[msg.confidence].label}
                              </span>
                            )}
                            {msg.refused && (
                              <Badge variant="critical" size="sm">No answer</Badge>
                            )}
                          </div>
                        )}

                        {msg.sources.length > 0 && (
                          <div className="pt-2 border-t border-border/40">
                            <span className="text-caption text-muted-foreground">Sources:</span>
                            {msg.sources.map((s, j) => (
                              <span key={j} className="text-caption text-accent">{s}{j < msg.sources.length - 1 ? ', ' : ''}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}

              {askMutation.isPending && (
                <div className="flex gap-3 animate-fade-in">
                  <div className="h-7 w-7 rounded-md bg-accent/10 grid place-items-center shrink-0">
                    <Loader2 className="h-3.5 w-3.5 text-accent animate-spin" />
                  </div>
                  <div className="bg-secondary/60 rounded-lg px-4 py-3">
                    <p className="text-body-sm text-muted-foreground">Thinking…</p>
                  </div>
                </div>
              )}

              {askMutation.isError && (
                <div className="rounded-lg bg-severity-critical/8 border border-severity-critical/20 px-4 py-3">
                  <p className="text-body-sm text-severity-critical">
                    Failed to get response. Is the backend running?
                  </p>
                </div>
              )}
            </div>
          </ScrollArea>

          <form onSubmit={handleSubmit} className="border-t border-border/60 px-4 py-3">
            <div className="flex gap-2">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ask about disease trends, policy, facility metrics…"
                disabled={askMutation.isPending}
                className="flex-1 h-9 px-3 rounded-md bg-secondary/60 border border-border text-body-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-accent/40 focus:ring-1 focus:ring-accent/20 disabled:opacity-50"
              />
              <Button
                type="submit"
                size="sm"
                disabled={!query.trim() || askMutation.isPending}
                className="shrink-0"
              >
                <Send className="h-3.5 w-3.5" />
              </Button>
            </div>
          </form>
        </Card>

        <div className="space-y-4">
          <Card className="overflow-hidden border-border/80">
            <div className="px-4 py-3 border-b border-border/60">
              <h3 className="text-subheading font-semibold tracking-tight">Recent AI Alerts</h3>
            </div>
            <ScrollArea className="h-[280px]">
              {recentAlertsQuery.isLoading ? (
                <div className="p-3 space-y-2">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="h-16 rounded-md" />
                  ))}
                </div>
              ) : (recentAlertsQuery.data ?? []).length === 0 ? (
                <div className="p-6 text-center">
                  <FileText className="h-6 w-6 text-muted-foreground/30 mx-auto mb-2" />
                  <p className="text-caption text-muted-foreground">No recent AI alerts</p>
                </div>
              ) : (
                <div className="p-2 space-y-1">
                  {(recentAlertsQuery.data ?? []).slice(0, 8).map((alert) => (
                    <div key={alert.id} className="rounded-md px-3 py-2 hover:bg-secondary/60 transition-colors">
                      <div className="flex items-center gap-2 mb-0.5">
                        <Badge
                          variant={alert.severity === 'HIGH' ? 'critical' : alert.severity === 'MEDIUM' ? 'warning' : 'secondary'}
                          size="sm"
                        >
                          {alert.severity}
                        </Badge>
                        {alert.llm_generated && (
                          <Badge variant="accent" size="sm">AI</Badge>
                        )}
                      </div>
                      <p className="text-body-sm font-medium text-foreground truncate">
                        {alert.facility_name || 'Unknown'}
                      </p>
                      <p className="text-caption text-muted-foreground truncate">
                        {alert.district_name}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          </Card>

          <Card className="p-4 border-border/80">
            <h3 className="text-subheading font-semibold tracking-tight mb-3">Model Status</h3>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-caption text-muted-foreground">Engine</span>
                <span className="text-caption font-medium text-foreground">Artem LLM v1</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-caption text-muted-foreground">RAG Source</span>
                <span className="text-caption font-medium text-foreground">Policy Docs</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-caption text-muted-foreground">Status</span>
                <span className="flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-success animate-pulse-dot" />
                  <span className="text-caption font-medium text-success">Online</span>
                </span>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </section>
  )
}
