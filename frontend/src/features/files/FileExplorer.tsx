import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, ChevronDown, FileCode, Folder, FolderOpen } from 'lucide-react'
import { files as filesApi } from '../../services/api/files'
import type { FileSummary } from '../../types/api'
import { useWorkspace } from '../workspace/WorkspaceContext'
import { Spinner } from '../../components/ui/Spinner'
import { ErrorMessage } from '../../components/ui/ErrorMessage'

interface TreeNode {
  name: string
  path: string
  type: 'file' | 'dir'
  file?: FileSummary
  children: TreeNode[]
}

function buildTree(items: FileSummary[]): TreeNode[] {
  const root: TreeNode = { name: '', path: '', type: 'dir', children: [] }

  for (const f of items) {
    const parts = f.path.replace(/\\/g, '/').split('/')
    let node = root
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i]
      const isLast = i === parts.length - 1
      const existing = node.children.find((c) => c.name === part)
      if (existing) {
        node = existing
      } else {
        const newNode: TreeNode = {
          name: part,
          path: parts.slice(0, i + 1).join('/'),
          type: isLast ? 'file' : 'dir',
          file: isLast ? f : undefined,
          children: [],
        }
        node.children.push(newNode)
        node = newNode
      }
    }
  }

  // Sort: dirs first, then files, alphabetically within each group
  function sort(nodes: TreeNode[]) {
    nodes.sort((a, b) => {
      if (a.type !== b.type) return a.type === 'dir' ? -1 : 1
      return a.name.localeCompare(b.name)
    })
    for (const n of nodes) sort(n.children)
  }
  sort(root.children)
  return root.children
}

function TreeNodeRow({
  node,
  depth,
}: {
  node: TreeNode
  depth: number
}) {
  const [open, setOpen] = useState(depth === 0)
  const { selectedFileId, navigateToSource } = useWorkspace()
  const isSelected = node.type === 'file' && node.file?.id === selectedFileId

  if (node.type === 'dir') {
    return (
      <>
        <button
          onClick={() => setOpen((v) => !v)}
          style={{
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            padding: `3px 8px 3px ${8 + depth * 14}px`,
            background: 'none',
            cursor: 'pointer',
            color: 'var(--color-text-2)',
            textAlign: 'left',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
          }}
          onMouseEnter={(e) =>
            ((e.currentTarget as HTMLButtonElement).style.background =
              'var(--color-surface-hover)')
          }
          onMouseLeave={(e) =>
            ((e.currentTarget as HTMLButtonElement).style.background = 'none')
          }
        >
          {open ? (
            <ChevronDown size={11} style={{ flexShrink: 0 }} />
          ) : (
            <ChevronRight size={11} style={{ flexShrink: 0 }} />
          )}
          {open ? (
            <FolderOpen size={12} style={{ flexShrink: 0, color: 'var(--color-accent)' }} />
          ) : (
            <Folder size={12} style={{ flexShrink: 0, color: 'var(--color-text-3)' }} />
          )}
          <span
            style={{
              fontSize: 12,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {node.name}
          </span>
        </button>
        {open &&
          node.children.map((child) => (
            <TreeNodeRow key={child.path} node={child} depth={depth + 1} />
          ))}
      </>
    )
  }

  return (
    <button
      onClick={() => {
        if (node.file) {
          navigateToSource(node.file.path)
        }
      }}
      style={{
        width: '100%',
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        padding: `3px 8px 3px ${8 + depth * 14}px`,
        background: isSelected ? 'var(--color-accent-dim)' : 'none',
        cursor: 'pointer',
        color: isSelected ? 'var(--color-accent)' : 'var(--color-text)',
        textAlign: 'left',
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        borderLeft: isSelected ? '1px solid var(--color-accent)' : '1px solid transparent',
      }}
      onMouseEnter={(e) => {
        if (!isSelected)
          (e.currentTarget as HTMLButtonElement).style.background = 'var(--color-surface-hover)'
      }}
      onMouseLeave={(e) => {
        if (!isSelected)
          (e.currentTarget as HTMLButtonElement).style.background = 'none'
      }}
    >
      <span style={{ width: 11, flexShrink: 0 }} />
      <FileCode size={12} style={{ flexShrink: 0, color: isSelected ? 'var(--color-accent)' : 'var(--color-text-3)' }} />
      <span
        style={{
          fontSize: 12,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          fontFamily: 'var(--font-mono)',
        }}
      >
        {node.name}
      </span>
    </button>
  )
}

export function FileExplorer() {
  const { repoId, setFilesByPath } = useWorkspace()

  const { data, isLoading, error } = useQuery({
    queryKey: ['files', repoId],
    queryFn: () => filesApi.list(repoId),
  })

  // Keep filesByPath map up to date
  useEffect(() => {
    if (data) {
      const map: Record<string, FileSummary> = {}
      for (const f of data.items) map[f.path] = f
      setFilesByPath(map)
    }
  }, [data, setFilesByPath])

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

  if (!data || data.items.length === 0) {
    return (
      <div style={{ padding: '12px 8px', color: 'var(--color-text-3)', fontSize: 12 }}>
        No files found. Ingest the repository first.
      </div>
    )
  }

  const tree = buildTree(data.items)

  return (
    <div style={{ overflowY: 'auto', overflowX: 'hidden', flex: 1 }}>
      {tree.map((node) => (
        <TreeNodeRow key={node.path} node={node} depth={0} />
      ))}
    </div>
  )
}
