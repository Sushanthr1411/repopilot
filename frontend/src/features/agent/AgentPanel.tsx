import { useState, useRef, useEffect, type FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Send, CheckCircle, XCircle, ChevronDown, ChevronUp, FileCode } from 'lucide-react'
import { agent as agentApi } from '../../services/api/agent'
import type { AgentToolEvent, AgentSource, AskResponse } from '../../types/api'
import { useWorkspace } from '../workspace/WorkspaceContext'
import { Spinner } from '../../components/ui/Spinner'
import { ErrorMessage } from '../../components/ui/ErrorMessage'

function AnswerText({ text }: { text: string }) {
  const lines = text.split('\n')
  return (
    <div style={{ fontSize: 13, lineHeight: 1.75, color: 'var(--color-text)' }}>
      {lines.map((line, i) => {
        // ### heading
        if (line.startsWith('### ')) {
          return (
            <div
              key={i}
              style={{
                fontWeight: 600,
                fontSize: 12,
                color: 'var(--color-text)',
                marginTop: i > 0 ? 10 : 0,
                marginBottom: 2,
              }}
            >
              {line.slice(4)}
            </div>
          )
        }
        // ## heading
        if (line.startsWith('## ')) {
          return (
            <div
              key={i}
              style={{
                fontWeight: 600,
                fontSize: 13,
                color: 'var(--color-text)',
                marginTop: i > 0 ? 12 : 0,
                marginBottom: 3,
              }}
            >
              {line.slice(3)}
            </div>
          )
        }
        // List item
        const listMatch = line.match(/^(\s*[-*]\s+)(.*)$/)
        if (listMatch) {
          const content = listMatch[2]
          const parts = content.split(/(`[^`]+`|\*\*[^*]+\*\*)/g)
          return (
            <div key={i} style={{ display: 'flex', gap: 6, marginTop: 2 }}>
              <span style={{ color: 'var(--color-text-3)', flexShrink: 0, marginTop: 1 }}>·</span>
              <span>{parts.map((p, j) => renderInline(p, j))}</span>
            </div>
          )
        }
        // Normal paragraph line
        const parts = line.split(/(`[^`]+`|\*\*[^*]+\*\*)/g)
        return (
          <span key={i}>
            {parts.map((p, j) => renderInline(p, j))}
            {i < lines.length - 1 && line.length > 0 && <br />}
            {i < lines.length - 1 && line.length === 0 && (
              <span style={{ display: 'block', height: 6 }} />
            )}
          </span>
        )
      })}
    </div>
  )
}

function renderInline(part: string, key: number) {
  if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
    return (
      <code
        key={key}
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          background: 'var(--color-surface-2)',
          padding: '1px 5px',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--color-accent-text)',
          border: '1px solid var(--color-border-2)',
        }}
      >
        {part.slice(1, -1)}
      </code>
    )
  }
  if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
    return (
      <strong key={key} style={{ fontWeight: 600, color: 'var(--color-text)' }}>
        {part.slice(2, -2)}
      </strong>
    )
  }
  return <span key={key}>{part}</span>
}

function ToolEventRow({ event }: { event: AgentToolEvent }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '2px 0',
        fontSize: 11,
        color: 'var(--color-text-2)',
      }}
    >
      {event.success ? (
        <CheckCircle size={10} style={{ color: 'var(--color-success)', flexShrink: 0 }} />
      ) : (
        <XCircle size={10} style={{ color: 'var(--color-error)', flexShrink: 0 }} />
      )}
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          color: 'var(--color-accent-text)',
          flexShrink: 0,
        }}
      >
        {event.tool_name}
      </span>
      <span
        style={{
          color: 'var(--color-text-3)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          flex: 1,
          minWidth: 0,
        }}
      >
        {event.arguments_summary}
      </span>
      <span
        style={{
          flexShrink: 0,
          color: 'var(--color-text-3)',
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
        }}
      >
        {event.duration_ms.toFixed(0)}ms
      </span>
    </div>
  )
}

function SourceChip({ source, onClick }: { source: AgentSource; onClick: () => void }) {
  const filename = source.file_path.split(/[/\\]/).pop() ?? source.file_path
  const dir = source.file_path.includes('/') || source.file_path.includes('\\')
    ? source.file_path.substring(0, source.file_path.length - filename.length - 1)
    : ''
  const range =
    source.start_line !== null && source.end_line !== null
      ? `:${source.start_line}–${source.end_line}`
      : source.start_line !== null
      ? `:${source.start_line}`
      : ''

  return (
    <button
      onClick={onClick}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        padding: '4px 8px',
        background: 'var(--color-surface-2)',
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius)',
        cursor: 'pointer',
        textAlign: 'left',
        transition: 'border-color 120ms, background 120ms',
        maxWidth: '100%',
        minWidth: 0,
      }}
      onMouseEnter={(e) => {
        ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--color-accent)'
        ;(e.currentTarget as HTMLButtonElement).style.background = 'var(--color-surface-hover)'
      }}
      onMouseLeave={(e) => {
        ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--color-border)'
        ;(e.currentTarget as HTMLButtonElement).style.background = 'var(--color-surface-2)'
      }}
    >
      <FileCode size={10} style={{ color: 'var(--color-text-3)', flexShrink: 0 }} />
      <span style={{ minWidth: 0, overflow: 'hidden' }}>
        {dir && (
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: 'var(--color-text-3)',
            }}
          >
            {dir}/
          </span>
        )}
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            color: 'var(--color-accent-text)',
          }}
        >
          {filename}
        </span>
        {range && (
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: 'var(--color-text-3)',
            }}
          >
            {range}
          </span>
        )}
        {source.symbol && (
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: 'var(--color-text-3)',
            }}
          >
            {' '}· {source.symbol}
          </span>
        )}
      </span>
    </button>
  )
}

interface ConversationEntry {
  question: string
  response: AskResponse
}

const EXAMPLE_PROMPTS = [
  'How does authentication work?',
  'What happens when a user is created?',
  'Explain the architecture of this repository.',
  'Which modules depend on the database layer?',
]

export function AgentPanel() {
  const { repoId, navigateToSource } = useWorkspace()
  const [question, setQuestion] = useState('')
  const [history, setHistory] = useState<ConversationEntry[]>([])
  const [expandedActivity, setExpandedActivity] = useState<Set<number>>(new Set())
  const scrollRef = useRef<HTMLDivElement>(null)

  const mutation = useMutation({
    mutationFn: (q: string) => agentApi.ask(repoId, { question: q }),
    onSuccess: (data, q) => {
      setHistory((prev) => {
        const idx = prev.length
        setExpandedActivity((s) => {
          const next = new Set(s)
          next.add(idx)
          return next
        })
        return [...prev, { question: q, response: data }]
      })
      setQuestion('')
    },
  })

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [history, mutation.isPending])

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const q = question.trim()
    if (!q || mutation.isPending) return
    mutation.mutate(q)
  }

  function toggleActivity(i: number) {
    setExpandedActivity((s) => {
      const next = new Set(s)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: 'var(--color-surface)',
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '10px 14px',
          borderBottom: '1px solid var(--color-border)',
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: 'var(--color-text-3)',
            textTransform: 'uppercase',
            letterSpacing: '0.07em',
          }}
        >
          AI Assistant
        </span>
        {history.length > 0 && (
          <button
            onClick={() => setHistory([])}
            style={{
              fontSize: 10,
              color: 'var(--color-text-3)',
              cursor: 'pointer',
              padding: '2px 6px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid transparent',
              transition: 'color 120ms, border-color 120ms',
            }}
            onMouseEnter={(e) => {
              ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--color-text-2)'
              ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--color-border)'
            }}
            onMouseLeave={(e) => {
              ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--color-text-3)'
              ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'transparent'
            }}
          >
            Clear
          </button>
        )}
      </div>

      {/* Conversation scroll area */}
      <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '14px' }}>

        {/* Empty state */}
        {history.length === 0 && !mutation.isPending && (
          <div>
            <div
              style={{
                color: 'var(--color-text-3)',
                fontSize: 12,
                lineHeight: 1.65,
                marginBottom: 16,
              }}
            >
              Ask anything about this repository. The agent searches code, inspects symbols, and
              traces dependencies to give grounded answers with source references.
            </div>
            <div
              style={{
                fontSize: 10,
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.07em',
                color: 'var(--color-text-3)',
                marginBottom: 8,
              }}
            >
              Try asking
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {EXAMPLE_PROMPTS.map((p) => (
                <button
                  key={p}
                  onClick={() => setQuestion(p)}
                  style={{
                    padding: '6px 10px',
                    background: 'var(--color-surface-2)',
                    border: '1px solid var(--color-border)',
                    borderRadius: 'var(--radius)',
                    fontSize: 12,
                    color: 'var(--color-text-2)',
                    textAlign: 'left',
                    cursor: 'pointer',
                    transition: 'border-color 120ms, color 120ms',
                  }}
                  onMouseEnter={(e) => {
                    ;(e.currentTarget as HTMLButtonElement).style.borderColor =
                      'var(--color-border-focus)'
                    ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--color-text)'
                  }}
                  onMouseLeave={(e) => {
                    ;(e.currentTarget as HTMLButtonElement).style.borderColor =
                      'var(--color-border)'
                    ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--color-text-2)'
                  }}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}

        {history.map((entry, i) => (
          <div key={i} style={{ marginBottom: 24 }}>
            {/* Question bubble */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'flex-end',
                marginBottom: 10,
              }}
            >
              <div
                style={{
                  maxWidth: '88%',
                  padding: '8px 12px',
                  background: 'var(--color-accent-dim)',
                  border: '1px solid color-mix(in srgb, var(--color-accent) 20%, transparent)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: 13,
                  color: 'var(--color-text)',
                  lineHeight: 1.5,
                }}
              >
                {entry.question}
              </div>
            </div>

            {/* Answer */}
            <AnswerText text={entry.response.answer} />

            {/* Agent activity (collapsible, per-entry) */}
            {entry.response.tools_used.length > 0 && (
              <div
                style={{
                  marginTop: 12,
                  border: '1px solid var(--color-border-2)',
                  borderRadius: 'var(--radius)',
                  overflow: 'hidden',
                }}
              >
                <button
                  onClick={() => toggleActivity(i)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 5,
                    width: '100%',
                    padding: '6px 10px',
                    background: 'var(--color-surface-2)',
                    fontSize: 10,
                    color: 'var(--color-text-3)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                    cursor: 'pointer',
                    border: 'none',
                    textAlign: 'left',
                  }}
                >
                  {expandedActivity.has(i) ? (
                    <ChevronUp size={10} />
                  ) : (
                    <ChevronDown size={10} />
                  )}
                  {entry.response.tools_used.length} tool calls · {entry.response.iterations} iterations
                  {entry.response.model && (
                    <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)' }}>
                      {entry.response.model.split('/').pop()}
                    </span>
                  )}
                </button>
                {expandedActivity.has(i) && (
                  <div style={{ padding: '6px 10px', background: 'var(--color-surface)' }}>
                    {entry.response.tools_used.map((ev, j) => (
                      <ToolEventRow key={j} event={ev} />
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Sources */}
            {entry.response.sources.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <div
                  style={{
                    fontSize: 10,
                    fontWeight: 600,
                    color: 'var(--color-text-3)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.07em',
                    marginBottom: 6,
                  }}
                >
                  Sources
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                  {entry.response.sources.map((src, j) => (
                    <SourceChip
                      key={j}
                      source={src}
                      onClick={() => {
                        if (src.start_line !== null) {
                          navigateToSource(
                            src.file_path,
                            src.start_line,
                            src.end_line ?? src.start_line,
                          )
                        } else {
                          navigateToSource(src.file_path)
                        }
                      }}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}

        {/* Pending state */}
        {mutation.isPending && (
          <div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'flex-end',
                marginBottom: 10,
              }}
            >
              <div
                style={{
                  maxWidth: '88%',
                  padding: '8px 12px',
                  background: 'var(--color-accent-dim)',
                  border: '1px solid color-mix(in srgb, var(--color-accent) 20%, transparent)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: 13,
                  color: 'var(--color-text)',
                  lineHeight: 1.5,
                }}
              >
                {question || '…'}
              </div>
            </div>
            <div
              style={{
                padding: '10px 12px',
                background: 'var(--color-surface-2)',
                borderRadius: 'var(--radius)',
                border: '1px solid var(--color-border-2)',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                fontSize: 12,
                color: 'var(--color-text-3)',
              }}
            >
              <Spinner size={11} />
              Agent is searching and reasoning…
            </div>
          </div>
        )}

        {mutation.isError && (
          <div style={{ marginTop: 8 }}>
            <ErrorMessage message={(mutation.error as Error).message} />
          </div>
        )}
      </div>

      {/* Input */}
      <form
        onSubmit={handleSubmit}
        style={{
          padding: '10px 12px',
          borderTop: '1px solid var(--color-border)',
          flexShrink: 0,
          display: 'flex',
          gap: 8,
          alignItems: 'flex-end',
        }}
      >
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about this repository… (Enter to send)"
          rows={2}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleSubmit(e as unknown as FormEvent)
            }
          }}
          style={{
            flex: 1,
            background: 'var(--color-surface-2)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius)',
            color: 'var(--color-text)',
            padding: '7px 10px',
            fontSize: 12,
            resize: 'none',
            outline: 'none',
            fontFamily: 'var(--font-sans)',
            lineHeight: 1.5,
            transition: 'border-color 120ms',
          }}
          onFocus={(e) => (e.target.style.borderColor = 'var(--color-accent)')}
          onBlur={(e) => (e.target.style.borderColor = 'var(--color-border)')}
        />
        <button
          type="submit"
          disabled={!question.trim() || mutation.isPending}
          style={{
            padding: '9px 11px',
            background:
              !question.trim() || mutation.isPending
                ? 'var(--color-surface-2)'
                : 'var(--color-accent)',
            border: '1px solid transparent',
            borderRadius: 'var(--radius)',
            color:
              !question.trim() || mutation.isPending
                ? 'var(--color-text-3)'
                : 'white',
            cursor: !question.trim() || mutation.isPending ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            transition: 'background 150ms',
          }}
          onMouseEnter={(e) => {
            if (question.trim() && !mutation.isPending)
              (e.currentTarget as HTMLButtonElement).style.background = 'var(--color-accent-hover)'
          }}
          onMouseLeave={(e) => {
            if (question.trim() && !mutation.isPending)
              (e.currentTarget as HTMLButtonElement).style.background = 'var(--color-accent)'
          }}
          title="Send (Enter)"
        >
          {mutation.isPending ? <Spinner size={14} /> : <Send size={14} />}
        </button>
      </form>
    </div>
  )
}
