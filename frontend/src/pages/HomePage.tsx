import { useState, useEffect, type FormEvent, type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { ArrowRight, Clock } from 'lucide-react'
import { repositories } from '../services/api/repositories'
import { Spinner } from '../components/ui/Spinner'

const RECENT_KEY = 'repopilot_recent'
const MAX_RECENT = 8

interface RecentRepo {
  id: string
  name: string
  path: string
  lastOpened: string
}

function loadRecent(): RecentRepo[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]')
  } catch {
    return []
  }
}

function saveRecent(repos: RecentRepo[]) {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(repos.slice(0, MAX_RECENT)))
  } catch {}
}

export function addToRecent(repo: { id: string; name: string; local_path: string | null }) {
  const next: RecentRepo = {
    id: repo.id,
    name: repo.name,
    path: repo.local_path ?? '',
    lastOpened: new Date().toISOString(),
  }
  const existing = loadRecent().filter((r) => r.id !== next.id)
  saveRecent([next, ...existing])
}

function formatDate(iso: string) {
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 86_400_000) return 'Today'
  if (diff < 172_800_000) return 'Yesterday'
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// The logo glyph — three nodes connected, representing a code graph
function LogoMark({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" aria-hidden>
      <circle cx="10" cy="10" r="3" fill="white" />
      <circle cx="17" cy="4"  r="2" fill="white" opacity="0.65" />
      <circle cx="3"  cy="16" r="2" fill="white" opacity="0.65" />
      <line x1="10" y1="10" x2="17" y2="4"  stroke="white" strokeWidth="1.2" opacity="0.4" />
      <line x1="10" y1="10" x2="3"  y2="16" stroke="white" strokeWidth="1.2" opacity="0.4" />
    </svg>
  )
}

export function HomePage() {
  const navigate = useNavigate()
  const [path, setPath] = useState('')
  const [recent, setRecent] = useState<RecentRepo[]>([])

  useEffect(() => {
    setRecent(loadRecent())
  }, [])

  const createMutation = useMutation({
    mutationFn: () =>
      repositories.create({
        name: path.trim().split(/[/\\]/).filter(Boolean).pop() ?? 'repo',
        local_path: path.trim(),
      }),
    onSuccess: (repo) => {
      addToRecent(repo)
      navigate(`/r/${repo.id}`)
    },
  })

  function handleSubmit(e: FormEvent | KeyboardEvent) {
    e.preventDefault()
    if (!path.trim() || createMutation.isPending) return
    createMutation.mutate()
  }

  const errorMsg =
    createMutation.isError && createMutation.error instanceof Error
      ? createMutation.error.message
      : null

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '32px 24px',
        background: 'var(--color-bg)',
        // Subtle radial glow from accent at top
        backgroundImage:
          'radial-gradient(ellipse 70% 35% at 50% -5%, color-mix(in srgb, var(--color-accent) 9%, transparent), transparent)',
      }}
    >
      <div
        className="fade-in"
        style={{ width: '100%', maxWidth: 460 }}
      >
        {/* ── Logo ──────────────────────────────────────── */}
        <div style={{ marginBottom: 40 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 16 }}>
            <div
              style={{
                width: 32,
                height: 32,
                background: 'var(--color-accent)',
                borderRadius: 'var(--radius)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
                boxShadow: '0 0 20px color-mix(in srgb, var(--color-accent) 30%, transparent)',
              }}
            >
              <LogoMark size={18} />
            </div>
            <span
              style={{
                fontSize: 16,
                fontWeight: 600,
                letterSpacing: '-0.025em',
                color: 'var(--color-text)',
              }}
            >
              RepoPilot AI
            </span>
          </div>

          <h1
            style={{
              margin: '0 0 8px',
              fontSize: 28,
              fontWeight: 600,
              letterSpacing: '-0.03em',
              lineHeight: 1.2,
              color: 'var(--color-text)',
            }}
          >
            Understand any Python codebase.
          </h1>
          <p
            style={{
              margin: 0,
              fontSize: 14,
              color: 'var(--color-text-2)',
              lineHeight: 1.6,
            }}
          >
            Static analysis · semantic search · AI grounding.
            <br />
            Ask questions, trace dependencies, navigate with evidence.
          </p>
        </div>

        {/* ── Input ─────────────────────────────────────── */}
        <div style={{ marginBottom: 32 }}>
          <label
            htmlFor="repo-path"
            className="section-label"
            style={{ display: 'block', marginBottom: 8 }}
          >
            Repository path
          </label>

          {/* Combined input + button row */}
          <div
            style={{
              display: 'flex',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius)',
              overflow: 'hidden',
              transition: 'border-color 120ms',
            }}
            onFocusCapture={(e) => {
              ;(e.currentTarget as HTMLDivElement).style.borderColor =
                'var(--color-accent)'
            }}
            onBlurCapture={(e) => {
              ;(e.currentTarget as HTMLDivElement).style.borderColor =
                'var(--color-border)'
            }}
          >
            <input
              id="repo-path"
              type="text"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit(e)}
              placeholder="C:\Users\you\projects\my-repo"
              autoFocus
              style={{
                flex: 1,
                background: 'var(--color-surface)',
                border: 'none',
                padding: '10px 13px',
                fontFamily: 'var(--font-mono)',
                fontSize: 12,
                color: 'var(--color-text)',
                outline: 'none',
                minWidth: 0,
              }}
            />
            <button
              onClick={handleSubmit}
              disabled={!path.trim() || createMutation.isPending}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '10px 16px',
                background:
                  !path.trim() || createMutation.isPending
                    ? 'var(--color-surface-2)'
                    : 'var(--color-accent)',
                color:
                  !path.trim() || createMutation.isPending
                    ? 'var(--color-text-3)'
                    : 'white',
                fontSize: 13,
                fontWeight: 500,
                cursor: !path.trim() || createMutation.isPending ? 'not-allowed' : 'pointer',
                transition: 'background 120ms, color 120ms',
                borderLeft: '1px solid var(--color-border)',
                whiteSpace: 'nowrap',
                flexShrink: 0,
              }}
              onMouseEnter={(e) => {
                if (path.trim() && !createMutation.isPending)
                  (e.currentTarget as HTMLButtonElement).style.background =
                    'var(--color-accent-hover)'
              }}
              onMouseLeave={(e) => {
                if (path.trim() && !createMutation.isPending)
                  (e.currentTarget as HTMLButtonElement).style.background =
                    'var(--color-accent)'
              }}
            >
              {createMutation.isPending ? (
                <>
                  <Spinner size={13} />
                  Registering…
                </>
              ) : (
                <>
                  Analyze
                  <ArrowRight size={13} />
                </>
              )}
            </button>
          </div>

          {errorMsg && (
            <div
              style={{
                marginTop: 8,
                fontSize: 12,
                color: 'var(--color-error)',
                display: 'flex',
                alignItems: 'center',
                gap: 5,
              }}
            >
              {errorMsg}
            </div>
          )}

          <div style={{ marginTop: 7, fontSize: 11, color: 'var(--color-text-3)' }}>
            Point to a directory containing Python source files. The name is inferred from the path.
          </div>
        </div>

        {/* ── Recent ────────────────────────────────────── */}
        {recent.length > 0 && (
          <div>
            <div
              className="section-label"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                marginBottom: 10,
              }}
            >
              <Clock size={10} />
              Recent
            </div>

            <div
              style={{
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius)',
                overflow: 'hidden',
              }}
            >
              {recent.map((r, i) => (
                <button
                  key={r.id}
                  onClick={() => navigate(`/r/${r.id}`)}
                  style={{
                    width: '100%',
                    display: 'grid',
                    gridTemplateColumns: '1fr auto',
                    alignItems: 'center',
                    padding: '10px 14px',
                    background: 'var(--color-surface)',
                    borderBottom:
                      i < recent.length - 1
                        ? '1px solid var(--color-border-2)'
                        : 'none',
                    textAlign: 'left',
                    cursor: 'pointer',
                    gap: 12,
                    transition: 'background 100ms',
                  }}
                  onMouseEnter={(e) =>
                    ((e.currentTarget as HTMLButtonElement).style.background =
                      'var(--color-surface-hover)')
                  }
                  onMouseLeave={(e) =>
                    ((e.currentTarget as HTMLButtonElement).style.background =
                      'var(--color-surface)')
                  }
                >
                  <div style={{ minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 500,
                        color: 'var(--color-text)',
                        marginBottom: 2,
                      }}
                    >
                      {r.name}
                    </div>
                    <div
                      style={{
                        fontSize: 11,
                        color: 'var(--color-text-3)',
                        fontFamily: 'var(--font-mono)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {r.path}
                    </div>
                  </div>
                  <div
                    style={{
                      fontSize: 11,
                      color: 'var(--color-text-3)',
                      flexShrink: 0,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                    }}
                  >
                    {formatDate(r.lastOpened)}
                    <ArrowRight size={12} style={{ color: 'var(--color-text-3)' }} />
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
