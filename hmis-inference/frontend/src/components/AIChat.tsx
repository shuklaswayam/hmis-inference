import { useState, useRef, useEffect } from 'react'
import { Send, Sparkles } from 'lucide-react'
import client from '@/api/client'

interface Message {
  role: 'user' | 'ai'
  text: string
  sources?: string[]
}

interface AIChatProps {
  onClose?: () => void
}

const SUGGESTED = [
  'Why are OPD visits high in Ahmedabad?',
  'Which districts need medicine restock urgently?',
  'What are the dengue outbreak response guidelines?',
]

export function AIChat({ onClose }: AIChatProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  const sendMessage = async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || isLoading) return

    setMessages(prev => [...prev, { role: 'user', text: trimmed }])
    setInput('')
    setIsLoading(true)

    try {
      const res = await client.post('/api/v1/ask', { query: trimmed })
      const data = res.data
      setMessages(prev => [
        ...prev,
        { role: 'ai', text: data.answer || 'No response generated.', sources: data.sources ?? [] },
      ])
    } catch {
      setMessages(prev => [
        ...prev,
        { role: 'ai', text: 'Failed to get a response. Is the backend running?' },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    sendMessage(input)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  return (
    <div className="flex flex-col h-full bg-card text-foreground">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border/40 shrink-0">
        <div className="h-6 w-6 rounded bg-accent/15 grid place-items-center">
          <Sparkles className="h-3.5 w-3.5 text-accent" />
        </div>
        <span className="text-body-sm font-semibold tracking-tight flex-1">Ask Artem</span>
        {onClose && (
          <button
            onClick={onClose}
            className="h-5 w-5 rounded hover:bg-secondary/60 flex items-center justify-center transition-colors text-muted-foreground hover:text-foreground"
            aria-label="Close AI chat"
          >
            <span className="text-sm leading-none font-medium">✕</span>
          </button>
        )}
      </div>

      {/* Message List */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3 text-[13px]">
        {messages.length === 0 && !isLoading && (
          <div className="py-6 text-center text-muted-foreground text-[12px] space-y-1">
            <Sparkles className="h-7 w-7 mx-auto text-accent/30 mb-2" />
            <p className="font-medium text-foreground/80">Ask anything about health data</p>
            <p className="text-[11px]">Powered by local RAG on policy documents and alerts.</p>
          </div>
        )}

        {messages.map((msg, i) =>
          msg.role === 'user' ? (
            /* User bubble — right-aligned blue */
            <div key={i} className="flex justify-end">
              <div className="max-w-[80%] bg-blue-600 text-white rounded-xl rounded-br-sm px-3 py-2 leading-snug">
                {msg.text}
              </div>
            </div>
          ) : (
            /* AI bubble — left-aligned gray */
            <div key={i} className="flex flex-col gap-1">
              <div className="max-w-[88%] bg-secondary/60 rounded-xl rounded-bl-sm px-3 py-2 leading-snug whitespace-pre-wrap">
                {msg.text}
              </div>
              {msg.sources && msg.sources.length > 0 && (
                <div className="flex flex-wrap gap-1 pl-1">
                  {msg.sources.map((s, j) => (
                    <span
                      key={j}
                      className="text-[10px] text-muted-foreground bg-secondary/40 border border-border/40 px-1.5 py-0.5 rounded"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )
        )}

        {/* Typing indicator */}
        {isLoading && (
          <div className="flex items-center gap-1 pl-1">
            <span className="typing-dot" />
            <span className="typing-dot" style={{ animationDelay: '0.15s' }} />
            <span className="typing-dot" style={{ animationDelay: '0.30s' }} />
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Suggested Question Chips */}
      {messages.length === 0 && !isLoading && (
        <div className="px-3 pb-2 flex flex-col gap-1 shrink-0">
          {SUGGESTED.map((q) => (
            <button
              key={q}
              onClick={() => sendMessage(q)}
              className="text-left text-[11px] text-muted-foreground hover:text-foreground bg-secondary/30 hover:bg-secondary/60 border border-border/40 hover:border-accent/30 px-3 py-2 rounded-lg transition-all"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <form
        onSubmit={handleSubmit}
        className="px-3 pb-3 pt-2 border-t border-border/30 shrink-0 space-y-2"
      >
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a health data question…"
            disabled={isLoading}
            className="flex-1 h-8 px-2.5 rounded-md bg-secondary/40 border border-border text-[12px] text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:border-accent/40 focus:ring-1 focus:ring-accent/20 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="h-8 w-8 rounded-md bg-accent hover:bg-accent/90 disabled:opacity-40 flex items-center justify-center transition-colors shrink-0"
            aria-label="Send"
          >
            <Send className="h-3.5 w-3.5 text-background" />
          </button>
        </div>

        {/* Footer */}
        <p className="text-[10px] text-muted-foreground/60 text-center leading-tight">
          Powered by Ollama + Gemma 3 • Local AI • No data leaves your machine
        </p>
      </form>
    </div>
  )
}
