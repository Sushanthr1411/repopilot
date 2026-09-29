import { useState, type FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { search as searchApi } from '../../services/api/search'
import type { SearchResultItem } from '../../types/api'
import { useWorkspace } from '../workspace/WorkspaceContext'
import { Spinner } from '../../components/ui/Spinner'
import { ErrorMessage } from '../../components/ui/ErrorMessage'
import { EmptyState } from '../../components/ui/EmptyState'

function ResultRow({ item }: { item: SearchResultItem }) {
  const { navigateToSource } = useWorkspace()

  return (
    <button
      onClick={() => navigateToSource(item.file_path, item.start_line, item.end_line)}
      style={{
        width: '100%',
        display: 'block',
        textAlign: 'left',
        padding: '10px 12px',
        borderBottom: '1px solid var(--color-border-2)',
        cursor: 'pointer',
        background: 'none',
      }}
      onMouseEnter={(e) =>
        ((e.currentTarget as HTMLButtonElement).style.background = 'var(--color-surface-hover)')
      }
      onMouseLeave={(e) =>
        ((e.currentTarget as HTMLButtonElement).style.background = 'none')
      }
    >
      {item.symbol_name && (
        <div
          style={{
            fontSize: 12,
            fontFamily: 'var(--font-mono)',
            color: 'var(--color-text)',
            marginBottom: 2,
            fontWeight: 500,
          }}
        >
          {item.symbol_name}
        </div>
      )}
      <div
        style={{
          fontSize: 11,
          fontFamily: 'var(--font-mono)',
          color: 'var(--color-accent)',
          marginBottom: 6,
        }}
      >
        {item.file_path}:{item.start_line}–{item.end_line}
      </div>
      <pre
        style={{
          margin: 0,
          fontSize: 11,
          fontFamily: 'var(--font-mono)',
          color: 'var(--color-text-2)',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
          lineHeight: 1.5,
          maxHeight: 80,
          overflow: 'hidden',
        }}
      >
        {item.content.trim()}
      </pre>
    </button>
  )
}

export function SearchPanel() {
  const { repoId } = useWorkspace()
  const [query, setQuery] = useState('')

  const mutation = useMutation({
    mutationFn: (q: string) => searchApi.query(repoId, { query: q, top_k: 10 }),
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const q = query.trim()
    if (q) mutation.mutate(q)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Search input */}
      <form
        onSubmit={handleSubmit}
        style={{
          padding: 8,
          borderBottom: '1px solid var(--color-border)',
          flexShrink: 0,
        }}
      >
        <div style={{ position: 'relative' }}>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Semantic search…"
            style={{
              width: '100%',
              background: 'var(--color-surface-2)',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--color-text)',
              padding: '6px 32px 6px 8px',
              fontSize: 12,
              outline: 'none',
            }}
            onFocus={(e) => (e.target.style.borderColor = 'var(--color-accent)')}
            onBlur={(e) => (e.target.style.borderColor = 'var(--color-border)')}
          />
          <button
            type="submit"
            disabled={!query.trim() || mutation.isPending}
            style={{
              position: 'absolute',
              right: 6,
              top: '50%',
              transform: 'translateY(-50%)',
              background: 'none',
              border: 'none',
              padding: 0,
              cursor: query.trim() ? 'pointer' : 'default',
              color: 'var(--color-text-3)',
              display: 'flex',
            }}
          >
            {mutation.isPending ? <Spinner size={13} /> : <Search size={13} />}
          </button>
        </div>
      </form>

      {/* Results */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {mutation.isError && (
          <div style={{ padding: 12 }}>
            <ErrorMessage message={(mutation.error as Error).message} compact />
          </div>
        )}
        {mutation.isSuccess && mutation.data.results.length === 0 && (
          <EmptyState title="No results" description="Try a different query." />
        )}
        {mutation.isSuccess &&
          mutation.data.results.map((r) => <ResultRow key={r.chunk_id} item={r} />)}
        {!mutation.isSuccess && !mutation.isError && (
          <EmptyState
            title="Search this repository"
            description="Describe what you're looking for in natural language."
          />
        )}
      </div>
    </div>
  )
}
