import { useParams, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Files,
  Braces,
  Search,
  GitFork,
  Code2,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  ChevronLeft,
  Play,
  RefreshCw,
} from 'lucide-react'
import { WorkspaceProvider, useWorkspace } from '../features/workspace/WorkspaceContext'
import { FileExplorer } from '../features/files/FileExplorer'
import { CodeViewer } from '../features/files/CodeViewer'
import { SymbolPanel } from '../features/symbols/SymbolPanel'
import { SearchPanel } from '../features/search/SearchPanel'
import { GraphPanel } from '../features/graph/GraphPanel'
import { AgentPanel } from '../features/agent/AgentPanel'
import { repositories } from '../services/api/repositories'
import { Spinner } from '../components/ui/Spinner'
import { ErrorMessage } from '../components/ui/ErrorMessage'
import { addToRecent } from './HomePage'
import type { LeftTab, ViewMode } from '../features/workspace/WorkspaceContext'

// Inner component that consumes the workspace context
function WorkspaceInner({ repoId }: { repoId: string }) {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const {
    leftTab, setLeftTab,
    leftCollapsed, setLeftCollapsed,
    rightCollapsed, setRightCollapsed,
    viewMode, setViewMode,
  } = useWorkspace()

  const { data: repo, isLoading, error } = useQuery({
    queryKey: ['repo', repoId],
    queryFn: () => repositories.get(repoId),
  })

  const ingestMutation = useMutation({
    mutationFn: () => repositories.ingest(repoId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['repo', repoId] })
      void qc.invalidateQueries({ queryKey: ['files', repoId] })
      void qc.invalidateQueries({ queryKey: ['symbols', repoId] })
      void qc.invalidateQueries({ queryKey: ['graph', repoId] })
    },
  })

  if (isLoading) {
    return (
      <div
        style={{
          height: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          color: 'var(--color-text-3)',
        }}
      >
        <Spinner />
        Loading repository…
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ padding: 24 }}>
        <ErrorMessage message={(error as Error).message} />
      </div>
    )
  }

  if (repo) addToRecent(repo)

  const isPending = repo?.status === 'pending'
  const isReady = repo?.status === 'ready'

  const tabs: { id: LeftTab; icon: React.ReactNode; label: string }[] = [
    { id: 'files', icon: <Files size={14} />, label: 'Files' },
    { id: 'symbols', icon: <Braces size={14} />, label: 'Symbols' },
    { id: 'search', icon: <Search size={14} />, label: 'Search' },
  ]

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        background: 'var(--color-bg)',
        overflow: 'hidden',
      }}
    >
      {/* App bar */}
      <div
        style={{
          height: 44,
          borderBottom: '1px solid var(--color-border)',
          display: 'flex',
          alignItems: 'center',
          padding: '0 10px',
          gap: 8,
          flexShrink: 0,
          background: 'var(--color-surface)',
        }}
      >
        {/* Back */}
        <button
          onClick={() => navigate('/')}
          style={{
            display: 'flex',
            alignItems: 'center',
            padding: '4px',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--color-text-3)',
            cursor: 'pointer',
            transition: 'color 120ms',
          }}
          onMouseEnter={(e) => {
            ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--color-text)'
            ;(e.currentTarget as HTMLButtonElement).style.background = 'var(--color-surface-hover)'
          }}
          onMouseLeave={(e) => {
            ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--color-text-3)'
            ;(e.currentTarget as HTMLButtonElement).style.background = 'none'
          }}
          title="Home"
        >
          <ChevronLeft size={15} />
        </button>

        {/* Divider */}
        <div style={{ width: 1, height: 18, background: 'var(--color-border)', flexShrink: 0 }} />

        {/* Logo mark */}
        <div
          style={{
            width: 22,
            height: 22,
            background: 'var(--color-accent)',
            borderRadius: 'var(--radius-sm)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <svg width="12" height="12" viewBox="0 0 20 20" fill="none">
            <circle cx="10" cy="10" r="3" fill="white" />
            <circle cx="17" cy="4"  r="2" fill="white" opacity="0.65" />
            <circle cx="3"  cy="16" r="2" fill="white" opacity="0.65" />
            <line x1="10" y1="10" x2="17" y2="4"  stroke="white" strokeWidth="1.2" opacity="0.4" />
            <line x1="10" y1="10" x2="3"  y2="16" stroke="white" strokeWidth="1.2" opacity="0.4" />
          </svg>
        </div>

        {/* Repo name */}
        <span
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: 'var(--color-text)',
            letterSpacing: '-0.02em',
          }}
        >
          {repo?.name}
        </span>

        {/* Status dot + label */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: isReady ? 'var(--color-success)' : 'var(--color-warning)',
              boxShadow: isReady
                ? '0 0 6px var(--color-success)'
                : '0 0 6px var(--color-warning)',
              flexShrink: 0,
            }}
          />
          <span
            style={{
              fontSize: 11,
              color: isReady ? 'var(--color-success)' : 'var(--color-warning)',
            }}
          >
            {repo?.status}
          </span>
        </div>

        {repo && (
          <span style={{ fontSize: 11, color: 'var(--color-text-3)', fontFamily: 'var(--font-mono)' }}>
            {repo.file_count} files · {repo.symbol_count} symbols
          </span>
        )}

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* View mode toggle */}
        <div
          style={{
            display: 'flex',
            background: 'var(--color-surface-2)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-sm)',
            overflow: 'hidden',
          }}
        >
          {([
            { id: 'code' as ViewMode, icon: <Code2 size={13} />, label: 'Code' },
            { id: 'graph' as ViewMode, icon: <GitFork size={13} />, label: 'Graph' },
          ] as const).map((m) => (
            <button
              key={m.id}
              onClick={() => setViewMode(m.id)}
              title={m.label}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                padding: '4px 9px',
                fontSize: 11,
                background: viewMode === m.id ? 'var(--color-surface-hover)' : 'none',
                color: viewMode === m.id ? 'var(--color-text)' : 'var(--color-text-3)',
                cursor: 'pointer',
                borderRight: m.id === 'code' ? '1px solid var(--color-border)' : 'none',
              }}
            >
              {m.icon}
              {m.label}
            </button>
          ))}
        </div>

        {/* Ingest / re-analyze */}
        {isPending ? (
          <button
            onClick={() => ingestMutation.mutate()}
            disabled={ingestMutation.isPending}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 5,
              padding: '5px 10px',
              background: 'var(--color-accent)',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              color: 'white',
              fontSize: 11,
              fontWeight: 500,
              cursor: ingestMutation.isPending ? 'not-allowed' : 'pointer',
            }}
          >
            {ingestMutation.isPending ? <Spinner size={12} /> : <Play size={12} />}
            Analyze
          </button>
        ) : (
          <button
            onClick={() => ingestMutation.mutate()}
            disabled={ingestMutation.isPending}
            title="Re-analyze"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              padding: '4px 8px',
              background: 'none',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--color-text-3)',
              fontSize: 11,
              cursor: ingestMutation.isPending ? 'not-allowed' : 'pointer',
            }}
          >
            {ingestMutation.isPending ? <Spinner size={12} /> : <RefreshCw size={12} />}
            Re-analyze
          </button>
        )}

        {/* Ingest error */}
        {ingestMutation.isError && (
          <span style={{ fontSize: 11, color: 'var(--color-error)' }}>
            {(ingestMutation.error as Error).message}
          </span>
        )}

        {/* Panel toggles */}
        <button
          onClick={() => setLeftCollapsed(!leftCollapsed)}
          title="Toggle file panel"
          style={{
            padding: '4px 5px',
            color: 'var(--color-text-3)',
            cursor: 'pointer',
            borderRadius: 'var(--radius-sm)',
            display: 'flex',
          }}
          onMouseEnter={(e) =>
            ((e.currentTarget as HTMLButtonElement).style.background = 'var(--color-surface-hover)')
          }
          onMouseLeave={(e) =>
            ((e.currentTarget as HTMLButtonElement).style.background = 'none')
          }
        >
          {leftCollapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
        </button>
        <button
          onClick={() => setRightCollapsed(!rightCollapsed)}
          title="Toggle AI panel"
          style={{
            padding: '4px 5px',
            color: 'var(--color-text-3)',
            cursor: 'pointer',
            borderRadius: 'var(--radius-sm)',
            display: 'flex',
          }}
          onMouseEnter={(e) =>
            ((e.currentTarget as HTMLButtonElement).style.background = 'var(--color-surface-hover)')
          }
          onMouseLeave={(e) =>
            ((e.currentTarget as HTMLButtonElement).style.background = 'none')
          }
        >
          {rightCollapsed ? <PanelRightOpen size={15} /> : <PanelRightClose size={15} />}
        </button>
      </div>

      {/* Pending state — show ingest prompt */}
      {isPending && !ingestMutation.isPending && (
        <div
          style={{
            padding: '10px 16px',
            background: 'color-mix(in srgb, var(--color-warning) 8%, transparent)',
            borderBottom: '1px solid color-mix(in srgb, var(--color-warning) 20%, transparent)',
            fontSize: 12,
            color: 'var(--color-warning)',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          Repository is registered but not yet analyzed. Click{' '}
          <strong>Analyze</strong> to parse and index it.
        </div>
      )}

      {/* Ingestion progress */}
      {ingestMutation.isPending && (
        <div
          style={{
            padding: '8px 16px',
            background: 'color-mix(in srgb, var(--color-accent) 8%, transparent)',
            borderBottom: '1px solid color-mix(in srgb, var(--color-accent) 20%, transparent)',
            fontSize: 12,
            color: 'var(--color-accent)',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <Spinner size={12} />
          Analyzing repository — parsing files, extracting symbols, building index…
        </div>
      )}

      {/* Three-panel workspace */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          overflow: 'hidden',
          minHeight: 0,
        }}
      >
        {/* Left panel */}
        <div
          style={{
            width: leftCollapsed ? 0 : 220,
            minWidth: leftCollapsed ? 0 : 220,
            borderRight: leftCollapsed ? 'none' : '1px solid var(--color-border)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            transition: 'width 180ms ease, min-width 180ms ease',
            background: 'var(--color-surface)',
          }}
        >
          {!leftCollapsed && (
            <>
              {/* Tab bar */}
              <div
                style={{
                  display: 'flex',
                  padding: '5px 6px',
                  gap: 2,
                  borderBottom: '1px solid var(--color-border)',
                  flexShrink: 0,
                  background: 'var(--color-surface)',
                }}
              >
                {tabs.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setLeftTab(t.id)}
                    title={t.label}
                    style={{
                      flex: 1,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 4,
                      padding: '5px 6px',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: 10,
                      fontWeight: 500,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      color: leftTab === t.id ? 'var(--color-text)' : 'var(--color-text-3)',
                      background:
                        leftTab === t.id ? 'var(--color-surface-3)' : 'none',
                      cursor: 'pointer',
                      transition: 'background 100ms, color 100ms',
                    }}
                    onMouseEnter={(e) => {
                      if (leftTab !== t.id)
                        (e.currentTarget as HTMLButtonElement).style.background =
                          'var(--color-surface-hover)'
                    }}
                    onMouseLeave={(e) => {
                      if (leftTab !== t.id)
                        (e.currentTarget as HTMLButtonElement).style.background = 'none'
                    }}
                  >
                    {t.icon}
                    {t.label}
                  </button>
                ))}
              </div>

              {/* Panel content */}
              <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                {leftTab === 'files' && <FileExplorer />}
                {leftTab === 'symbols' && <SymbolPanel />}
                {leftTab === 'search' && <SearchPanel />}
              </div>
            </>
          )}
        </div>

        {/* Center panel */}
        <div
          style={{
            flex: 1,
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
            minWidth: 0,
          }}
        >
          {viewMode === 'code' ? <CodeViewer /> : <GraphPanel />}
        </div>

        {/* Right panel */}
        <div
          style={{
            width: rightCollapsed ? 0 : 320,
            minWidth: rightCollapsed ? 0 : 320,
            borderLeft: rightCollapsed ? 'none' : '1px solid var(--color-border)',
            overflow: 'hidden',
            transition: 'width 180ms ease, min-width 180ms ease',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {!rightCollapsed && <AgentPanel />}
        </div>
      </div>
    </div>
  )
}

export function RepositoryWorkspacePage() {
  const { repoId } = useParams<{ repoId: string }>()

  if (!repoId) {
    return <div style={{ padding: 24, color: 'var(--color-error)' }}>Missing repository ID</div>
  }

  return (
    <WorkspaceProvider repoId={repoId}>
      <WorkspaceInner repoId={repoId} />
    </WorkspaceProvider>
  )
}
