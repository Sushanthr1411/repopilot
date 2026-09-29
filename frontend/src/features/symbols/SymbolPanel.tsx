import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Braces, FunctionSquare, Box, Layers } from 'lucide-react'
import { symbols as symbolsApi } from '../../services/api/symbols'
import { graph as graphApi } from '../../services/api/graph'
import type { SymbolResponse } from '../../types/api'
import { useWorkspace } from '../workspace/WorkspaceContext'
import { Spinner } from '../../components/ui/Spinner'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorMessage } from '../../components/ui/ErrorMessage'

function SymbolIcon({ type }: { type: string }) {
  const style = { flexShrink: 0, width: 13, height: 13 }
  if (type === 'class') return <Box size={13} style={{ ...style, color: '#64b5f6' }} />
  if (type === 'function' || type === 'async_function')
    return <FunctionSquare size={13} style={{ ...style, color: '#a5d6a7' }} />
  if (type === 'method') return <Braces size={13} style={{ ...style, color: '#ffcc80' }} />
  return <Layers size={13} style={{ ...style, color: 'var(--color-text-3)' }} />
}

function SymbolDetail({ symbol }: { symbol: SymbolResponse }) {
  const { repoId, navigateToSource } = useWorkspace()

  const { data: callers } = useQuery({
    queryKey: ['callers', repoId, symbol.id],
    queryFn: () => graphApi.callers(repoId, symbol.id),
  })
  const { data: callees } = useQuery({
    queryKey: ['callees', repoId, symbol.id],
    queryFn: () => graphApi.callees(repoId, symbol.id),
  })

  return (
    <div style={{ padding: '12px', fontSize: 12 }}>
      {/* Symbol header */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
          <SymbolIcon type={symbol.symbol_type} />
          <span style={{ fontWeight: 600, color: 'var(--color-text)', fontFamily: 'var(--font-mono)' }}>
            {symbol.name}
          </span>
        </div>
        <div style={{ color: 'var(--color-text-3)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
          {symbol.symbol_type}
        </div>
      </div>

      {/* Location */}
      <button
        onClick={() =>
          navigateToSource(symbol.file_path, symbol.start_line, symbol.end_line)
        }
        style={{
          display: 'block',
          width: '100%',
          textAlign: 'left',
          padding: '6px 8px',
          background: 'var(--color-surface-2)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-sm)',
          marginBottom: 12,
          cursor: 'pointer',
          color: 'var(--color-accent)',
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
        }}
        onMouseEnter={(e) =>
          ((e.currentTarget as HTMLButtonElement).style.background = 'var(--color-surface-hover)')
        }
        onMouseLeave={(e) =>
          ((e.currentTarget as HTMLButtonElement).style.background = 'var(--color-surface-2)')
        }
      >
        {symbol.file_path}:{symbol.start_line}–{symbol.end_line}
      </button>

      {/* Signature */}
      {symbol.signature && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 10, color: 'var(--color-text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>
            Signature
          </div>
          <code
            style={{
              display: 'block',
              background: 'var(--color-surface-2)',
              padding: '6px 8px',
              borderRadius: 'var(--radius-sm)',
              fontSize: 11,
              color: 'var(--color-text)',
              overflowX: 'auto',
              whiteSpace: 'nowrap',
            }}
          >
            {symbol.signature}
          </code>
        </div>
      )}

      {/* Docstring */}
      {symbol.docstring && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 10, color: 'var(--color-text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>
            Docstring
          </div>
          <div
            style={{
              color: 'var(--color-text-2)',
              fontSize: 12,
              lineHeight: 1.6,
              maxHeight: 120,
              overflowY: 'auto',
            }}
          >
            {symbol.docstring}
          </div>
        </div>
      )}

      {/* Relationships */}
      {((callers && callers.length > 0) || (callees && callees.length > 0)) && (
        <div>
          <div style={{ fontSize: 10, color: 'var(--color-text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
            Relationships
          </div>
          {callers && callers.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 11, color: 'var(--color-text-3)', marginBottom: 4 }}>Called by</div>
              {callers.map((c) => (
                <button
                  key={c.symbol_id}
                  onClick={() => navigateToSource(c.file_path, c.start_line, c.end_line)}
                  style={{
                    display: 'block',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    color: 'var(--color-text-2)',
                    marginBottom: 2,
                    cursor: 'pointer',
                    background: 'none',
                    border: 'none',
                    padding: 0,
                    textAlign: 'left',
                  }}
                  onMouseEnter={(e) =>
                    ((e.currentTarget as HTMLButtonElement).style.color = 'var(--color-accent)')
                  }
                  onMouseLeave={(e) =>
                    ((e.currentTarget as HTMLButtonElement).style.color = 'var(--color-text-2)')
                  }
                >
                  {c.name}
                </button>
              ))}
            </div>
          )}
          {callees && callees.length > 0 && (
            <div>
              <div style={{ fontSize: 11, color: 'var(--color-text-3)', marginBottom: 4 }}>Calls</div>
              {callees.map((c) => (
                <button
                  key={c.symbol_id}
                  onClick={() => navigateToSource(c.file_path, c.start_line, c.end_line)}
                  style={{
                    display: 'block',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    color: 'var(--color-text-2)',
                    marginBottom: 2,
                    cursor: 'pointer',
                    background: 'none',
                    border: 'none',
                    padding: 0,
                    textAlign: 'left',
                  }}
                  onMouseEnter={(e) =>
                    ((e.currentTarget as HTMLButtonElement).style.color = 'var(--color-accent)')
                  }
                  onMouseLeave={(e) =>
                    ((e.currentTarget as HTMLButtonElement).style.color = 'var(--color-text-2)')
                  }
                >
                  {c.name}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function SymbolPanel() {
  const { repoId, selectedSymbolId, selectSymbol, navigateToSource } = useWorkspace()
  const [search, setSearch] = useState('')

  const { data, isLoading, error } = useQuery({
    queryKey: ['symbols', repoId],
    queryFn: () => symbolsApi.list(repoId),
  })

  const { data: selectedSymbol } = useQuery({
    queryKey: ['symbol', repoId, selectedSymbolId],
    queryFn: () => symbolsApi.get(repoId, selectedSymbolId!),
    enabled: !!selectedSymbolId,
  })

  const filtered = data?.items.filter(
    (s) =>
      !search ||
      s.name.toLowerCase().includes(search.toLowerCase()) ||
      s.file_path.toLowerCase().includes(search.toLowerCase()),
  )

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 20 }}>
        <Spinner />
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ padding: 12 }}>
        <ErrorMessage message={(error as Error).message} compact />
      </div>
    )
  }

  if (selectedSymbol && selectedSymbolId) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflowY: 'auto' }}>
        <div
          style={{
            padding: '6px 8px',
            borderBottom: '1px solid var(--color-border)',
            flexShrink: 0,
          }}
        >
          <button
            onClick={() => selectSymbol(null)}
            style={{
              fontSize: 11,
              color: 'var(--color-text-3)',
              cursor: 'pointer',
              padding: 0,
              background: 'none',
              border: 'none',
            }}
            onMouseEnter={(e) =>
              ((e.currentTarget as HTMLButtonElement).style.color = 'var(--color-accent)')
            }
            onMouseLeave={(e) =>
              ((e.currentTarget as HTMLButtonElement).style.color = 'var(--color-text-3)')
            }
          >
            ← All symbols
          </button>
        </div>
        <SymbolDetail symbol={selectedSymbol} />
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Search input */}
      <div style={{ padding: '8px', borderBottom: '1px solid var(--color-border)', flexShrink: 0 }}>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter symbols…"
          style={{
            width: '100%',
            background: 'var(--color-surface-2)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--color-text)',
            padding: '5px 8px',
            fontSize: 12,
            outline: 'none',
          }}
        />
      </div>

      {/* Symbol list */}
      <div style={{ overflowY: 'auto', flex: 1 }}>
        {filtered?.length === 0 && <EmptyState title="No symbols found" />}
        {filtered?.map((sym) => (
          <button
            key={sym.id}
            onClick={() => {
              selectSymbol(sym.id)
              navigateToSource(sym.file_path, sym.start_line, sym.end_line)
            }}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'flex-start',
              gap: 6,
              padding: '6px 10px',
              background: sym.id === selectedSymbolId ? 'var(--color-accent-dim)' : 'none',
              cursor: 'pointer',
              textAlign: 'left',
              borderBottom: '1px solid var(--color-border-2)',
            }}
            onMouseEnter={(e) => {
              if (sym.id !== selectedSymbolId)
                (e.currentTarget as HTMLButtonElement).style.background =
                  'var(--color-surface-hover)'
            }}
            onMouseLeave={(e) => {
              if (sym.id !== selectedSymbolId)
                (e.currentTarget as HTMLButtonElement).style.background = 'none'
            }}
          >
            <SymbolIcon type={sym.symbol_type} />
            <div>
              <div
                style={{
                  fontSize: 12,
                  color: 'var(--color-text)',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {sym.name}
              </div>
              <div
                style={{
                  fontSize: 11,
                  color: 'var(--color-text-3)',
                  fontFamily: 'var(--font-mono)',
                  marginTop: 1,
                }}
              >
                {sym.file_path}:{sym.start_line}
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
