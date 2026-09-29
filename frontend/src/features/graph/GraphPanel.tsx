import { useMemo, useCallback, useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  type NodeTypes,
  Handle,
  Position,
  MarkerType,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { Braces, Code2, Package, Hash, Search, X, ChevronDown } from 'lucide-react'
import { graph as graphApi } from '../../services/api/graph'
import type { GraphNode } from '../../types/api'
import { useWorkspace } from '../workspace/WorkspaceContext'
import { Spinner } from '../../components/ui/Spinner'
import { ErrorMessage } from '../../components/ui/ErrorMessage'
import { EmptyState } from '../../components/ui/EmptyState'

// ── Thresholds ─────────────────────────────────────────────────────────────

const NODE_RENDER_LIMIT = 200

// ── Color palette ──────────────────────────────────────────────────────────

interface SymbolStyle { main: string; dim: string; bg: string }

const SYMBOL_STYLES: Record<string, SymbolStyle> = {
  class:          { main: '#7b68ee', dim: '#7b68ee50', bg: '#7b68ee14' },
  function:       { main: '#4db87a', dim: '#4db87a50', bg: '#4db87a14' },
  async_function: { main: '#3db4ca', dim: '#3db4ca50', bg: '#3db4ca14' },
  method:         { main: '#e8a050', dim: '#e8a05050', bg: '#e8a05014' },
  module:         { main: '#aa78e0', dim: '#aa78e050', bg: '#aa78e014' },
}
const DEFAULT_STYLE: SymbolStyle = { main: '#6868a0', dim: '#6868a050', bg: '#6868a014' }

const EDGE_COLORS: Record<string, string> = {
  CALLS:   '#7b68ee',
  IMPORTS: '#3db4ca',
  INHERITS:'#e8a050',
  DEFINES: '#4db87a',
  USES:    '#7878a0',
}

const HANDLE_STYLE = { width: 7, height: 7, border: '1.5px solid #09090e' }

// ── TypeIcon ───────────────────────────────────────────────────────────────

function TypeIcon({ type, color }: { type: string; color: string }) {
  const props = { size: 10, color, style: { flexShrink: 0 } as React.CSSProperties }
  if (type === 'class')                                 return <Braces {...props} />
  if (type === 'module')                                return <Package {...props} />
  if (type === 'function' || type === 'async_function') return <Code2 {...props} />
  if (type === 'method')                                return <Hash {...props} />
  return <Code2 {...props} />
}

// ── SymbolNode ─────────────────────────────────────────────────────────────

function SymbolNode({
  data,
  selected,
}: {
  data: { label: string; type: string; file: string; line: number }
  selected?: boolean
}) {
  const [hovered, setHovered] = useState(false)
  const s = SYMBOL_STYLES[data.type] ?? DEFAULT_STYLE
  const active = selected || hovered
  const filename = data.file.split(/[/\\]/).pop() ?? data.file

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        minWidth: 164,
        maxWidth: 224,
        borderRadius: 7,
        border: `1px solid ${active ? s.main + 'cc' : s.main + '38'}`,
        borderLeft: `3px solid ${s.main}`,
        background: 'linear-gradient(140deg, #14141d 0%, #1a1a26 100%)',
        padding: '9px 11px 9px 10px',
        boxShadow: active
          ? `0 0 0 1px ${s.dim}, 0 8px 32px ${s.dim}, 0 2px 8px #00000080`
          : `0 2px 12px #00000060, 0 1px 2px #00000040`,
        transition: 'box-shadow 180ms ease, border-color 180ms ease',
        cursor: 'pointer',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ ...HANDLE_STYLE, background: s.main }} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
        <TypeIcon type={data.type} color={s.main} />
        <span
          style={{
            fontFamily: 'var(--font-mono, monospace)',
            fontSize: 12,
            fontWeight: 600,
            color: active ? '#eeeef8' : '#d8d8e8',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            flex: 1,
            transition: 'color 180ms',
          }}
        >
          {data.label}
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6, minWidth: 0 }}>
        <span
          style={{
            flexShrink: 0,
            fontSize: 9,
            padding: '1px 5px',
            borderRadius: 3,
            background: s.bg,
            color: s.main,
            fontFamily: 'var(--font-mono, monospace)',
            fontWeight: 600,
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
          }}
        >
          {data.type.replace('_', ' ')}
        </span>
        <span
          style={{
            fontSize: 10,
            color: active ? '#5a5a78' : '#3e3e56',
            fontFamily: 'var(--font-mono, monospace)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            flex: 1,
            transition: 'color 180ms',
          }}
        >
          {filename}:{data.line}
        </span>
      </div>

      <Handle type="source" position={Position.Bottom} style={{ ...HANDLE_STYLE, background: s.main }} />
    </div>
  )
}

const nodeTypes: NodeTypes = { symbol: SymbolNode }

// ── Layout ─────────────────────────────────────────────────────────────────

function layoutNodes(graphNodes: GraphNode[]): Record<string, { x: number; y: number }> {
  const byFile: Record<string, GraphNode[]> = {}
  for (const n of graphNodes) { ;(byFile[n.file_path] ??= []).push(n) }
  for (const nodes of Object.values(byFile)) nodes.sort((a, b) => a.start_line - b.start_line)
  const files = Object.keys(byFile).sort()
  const positions: Record<string, { x: number; y: number }> = {}
  files.forEach((file, fi) => {
    byFile[file].forEach((node, ni) => {
      positions[node.symbol_id] = { x: fi * 300, y: ni * 115 }
    })
  })
  return positions
}

// ── Legend ─────────────────────────────────────────────────────────────────

function Legend() {
  return (
    <div
      style={{
        position: 'absolute',
        bottom: 80,
        left: 16,
        background: 'rgba(11, 11, 18, 0.92)',
        backdropFilter: 'blur(12px)',
        border: '1px solid #23233a',
        borderRadius: 8,
        padding: '10px 13px',
        zIndex: 10,
        userSelect: 'none',
      }}
    >
      <div style={legendHeadingStyle}>Symbols</div>
      {Object.entries(SYMBOL_STYLES).map(([type, s]) => (
        <div key={type} style={legendRowStyle}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: s.main, flexShrink: 0, boxShadow: `0 0 5px ${s.main}` }} />
          <span style={legendLabelStyle}>{type.replace('_', ' ')}</span>
        </div>
      ))}
      <div style={{ height: 1, background: '#23233a', margin: '8px 0' }} />
      <div style={legendHeadingStyle}>Relationships</div>
      {Object.entries(EDGE_COLORS).map(([rel, color]) => (
        <div key={rel} style={legendRowStyle}>
          <div style={{ width: 14, height: 2, background: color, borderRadius: 2, flexShrink: 0, boxShadow: `0 0 4px ${color}` }} />
          <span style={legendLabelStyle}>{rel.toLowerCase()}</span>
        </div>
      ))}
    </div>
  )
}

const legendHeadingStyle: React.CSSProperties = { fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.09em', color: '#3c3c58', marginBottom: 6 }
const legendRowStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 7, marginBottom: 5 }
const legendLabelStyle: React.CSSProperties = { fontSize: 10, color: '#6a6a8a', fontFamily: 'var(--font-mono, monospace)' }

// ── Stats bar ──────────────────────────────────────────────────────────────

function StatsBar({ nodeCount, edgeCount, visibleNodes, totalNodes }: { nodeCount: number; edgeCount: number; visibleNodes?: number; totalNodes?: number }) {
  const filtered = visibleNodes !== undefined && totalNodes !== undefined && visibleNodes < totalNodes

  return (
    <div
      style={{
        position: 'absolute',
        top: 12,
        left: '50%',
        transform: 'translateX(-50%)',
        background: 'rgba(11, 11, 18, 0.88)',
        backdropFilter: 'blur(12px)',
        border: '1px solid #23233a',
        borderRadius: 20,
        padding: '5px 14px',
        zIndex: 10,
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        userSelect: 'none',
        pointerEvents: 'none',
      }}
    >
      <span style={{ fontSize: 11, color: '#6a6a8a', fontFamily: 'var(--font-mono, monospace)' }}>
        {filtered ? (
          <><strong style={{ color: '#a0a0c0' }}>{nodeCount}</strong> / {totalNodes} symbols</>
        ) : (
          <><strong style={{ color: '#a0a0c0' }}>{nodeCount}</strong> symbols</>
        )}
      </span>
      <span style={{ width: 1, height: 12, background: '#23233a' }} />
      <span style={{ fontSize: 11, color: '#6a6a8a', fontFamily: 'var(--font-mono, monospace)' }}>
        <strong style={{ color: '#a0a0c0' }}>{edgeCount}</strong> relationships
      </span>
    </div>
  )
}

// ── File filter ────────────────────────────────────────────────────────────

function FileFilterPanel({
  files,
  selected,
  onChange,
}: {
  files: string[]
  selected: Set<string>
  onChange: (s: Set<string>) => void
}) {
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)

  const filtered = useMemo(
    () => files.filter((f) => f.toLowerCase().includes(search.toLowerCase())),
    [files, search],
  )

  function toggle(file: string) {
    const next = new Set(selected)
    if (next.has(file)) next.delete(file)
    else next.add(file)
    onChange(next)
  }

  function clearAll() { onChange(new Set()) }

  const btnLabel =
    selected.size === 0
      ? `Filter by file (${files.length} files)`
      : `${selected.size} file${selected.size === 1 ? '' : 's'} selected`

  return (
    <div style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '5px 10px',
          background: selected.size > 0 ? 'color-mix(in srgb, #7b68ee 15%, #0e0e18)' : '#0e0e18',
          border: `1px solid ${selected.size > 0 ? '#7b68ee66' : '#26263a'}`,
          borderRadius: 6,
          fontSize: 11,
          color: selected.size > 0 ? '#a89ff7' : '#6a6a8a',
          cursor: 'pointer',
          whiteSpace: 'nowrap',
          transition: 'all 120ms',
          fontFamily: 'var(--font-mono, monospace)',
        }}
      >
        <Search size={10} />
        {btnLabel}
        <ChevronDown size={10} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 150ms' }} />
      </button>

      {selected.size > 0 && (
        <button
          onClick={clearAll}
          title="Clear filter"
          style={{
            position: 'absolute',
            right: -24,
            top: '50%',
            transform: 'translateY(-50%)',
            padding: 3,
            color: '#48485e',
            cursor: 'pointer',
            borderRadius: 4,
            display: 'flex',
          }}
        >
          <X size={12} />
        </button>
      )}

      {open && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            left: 0,
            minWidth: 280,
            maxWidth: 360,
            background: '#0d0d16',
            border: '1px solid #26263a',
            borderRadius: 8,
            boxShadow: '0 8px 32px #00000080',
            zIndex: 30,
            overflow: 'hidden',
          }}
        >
          {/* Search */}
          <div style={{ padding: '8px 10px', borderBottom: '1px solid #1e1e2c' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, background: '#14141e', borderRadius: 5, padding: '5px 9px', border: '1px solid #26263a' }}>
              <Search size={11} style={{ color: '#404058', flexShrink: 0 }} />
              <input
                autoFocus
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search files…"
                style={{
                  flex: 1,
                  background: 'none',
                  border: 'none',
                  outline: 'none',
                  color: '#c8c8e0',
                  fontSize: 11,
                  fontFamily: 'var(--font-mono, monospace)',
                }}
              />
            </div>
          </div>

          {/* File list */}
          <div style={{ maxHeight: 240, overflowY: 'auto', padding: '4px 0' }}>
            {filtered.length === 0 && (
              <div style={{ padding: '10px 12px', fontSize: 11, color: '#404058', textAlign: 'center' }}>
                No files match
              </div>
            )}
            {filtered.map((file) => {
              const isSelected = selected.has(file)
              const shortName = file.split(/[/\\]/).pop() ?? file
              const dir = file.length > shortName.length ? file.slice(0, file.length - shortName.length - 1) : ''
              return (
                <button
                  key={file}
                  onClick={() => toggle(file)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    width: '100%',
                    padding: '5px 12px',
                    background: isSelected ? '#7b68ee12' : 'none',
                    cursor: 'pointer',
                    textAlign: 'left',
                    transition: 'background 100ms',
                    border: 'none',
                  }}
                  onMouseEnter={(e) => {
                    if (!isSelected) (e.currentTarget as HTMLButtonElement).style.background = '#16162a'
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected) (e.currentTarget as HTMLButtonElement).style.background = 'none'
                  }}
                >
                  {/* Checkbox dot */}
                  <span
                    style={{
                      width: 13,
                      height: 13,
                      borderRadius: 3,
                      border: `1px solid ${isSelected ? '#7b68ee' : '#3a3a56'}`,
                      background: isSelected ? '#7b68ee' : 'none',
                      flexShrink: 0,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    {isSelected && (
                      <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                        <path d="M1.5 4L3.5 6L6.5 2" stroke="white" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    )}
                  </span>
                  <span style={{ minWidth: 0 }}>
                    {dir && (
                      <span style={{ fontSize: 10, color: '#3e3e56', fontFamily: 'var(--font-mono, monospace)' }}>{dir}/</span>
                    )}
                    <span style={{ fontSize: 11, color: isSelected ? '#c0b8f8' : '#9090b0', fontFamily: 'var(--font-mono, monospace)' }}>{shortName}</span>
                  </span>
                </button>
              )
            })}
          </div>

          {/* Footer */}
          <div style={{ padding: '7px 12px', borderTop: '1px solid #1e1e2c', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 10, color: '#404058' }}>{selected.size} selected</span>
            <div style={{ display: 'flex', gap: 8 }}>
              {selected.size > 0 && (
                <button
                  onClick={clearAll}
                  style={{ fontSize: 10, color: '#6060a0', cursor: 'pointer', padding: '2px 6px', borderRadius: 4, border: '1px solid #26263a', background: 'none', transition: 'color 120ms' }}
                >
                  Clear
                </button>
              )}
              <button
                onClick={() => setOpen(false)}
                style={{ fontSize: 10, color: '#9090c0', cursor: 'pointer', padding: '2px 6px', borderRadius: 4, border: '1px solid #7b68ee44', background: '#7b68ee12' }}
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── GraphPanel ─────────────────────────────────────────────────────────────

export function GraphPanel() {
  const { repoId, navigateToSource, selectSymbol } = useWorkspace()
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set())

  const { data, isLoading, error } = useQuery({
    queryKey: ['graph', repoId],
    queryFn: () => graphApi.get(repoId),
  })

  const isLarge = (data?.nodes.length ?? 0) > NODE_RENDER_LIMIT

  // All unique files sorted
  const allFiles = useMemo(
    () => [...new Set((data?.nodes ?? []).map((n) => n.file_path))].sort(),
    [data],
  )

  // Adjacency map for neighbor expansion
  const neighborMap = useMemo(() => {
    const map: Record<string, Set<string>> = {}
    for (const e of data?.edges ?? []) {
      ;(map[e.source_symbol_id] ??= new Set()).add(e.target_symbol_id)
      ;(map[e.target_symbol_id] ??= new Set()).add(e.source_symbol_id)
    }
    return map
  }, [data])

  // Filtered node/edge lists
  const { visibleNodes, visibleEdges } = useMemo(() => {
    if (!data) return { visibleNodes: [], visibleEdges: [] }

    let nodes = data.nodes
    if (selectedFiles.size > 0) {
      // Primary nodes from selected files
      const primaryIds = new Set(
        data.nodes.filter((n) => selectedFiles.has(n.file_path)).map((n) => n.symbol_id),
      )
      // Expand to include direct neighbors (so we see relationships)
      const expanded = new Set(primaryIds)
      for (const id of primaryIds) {
        for (const nId of neighborMap[id] ?? []) expanded.add(nId)
      }
      nodes = data.nodes.filter((n) => expanded.has(n.symbol_id))
    } else if (isLarge) {
      // Too large and no filter — return empty to show the filter prompt
      return { visibleNodes: [], visibleEdges: [] }
    }

    const visibleIds = new Set(nodes.map((n) => n.symbol_id))
    const edges = data.edges.filter(
      (e) => visibleIds.has(e.source_symbol_id) && visibleIds.has(e.target_symbol_id),
    )
    return { visibleNodes: nodes, visibleEdges: edges }
  }, [data, selectedFiles, neighborMap, isLarge])

  const positions = useMemo(() => layoutNodes(visibleNodes), [visibleNodes])

  const initialNodes: Node[] = useMemo(
    () =>
      visibleNodes.map((n) => ({
        id: n.symbol_id,
        type: 'symbol',
        position: positions[n.symbol_id] ?? { x: 0, y: 0 },
        data: { label: n.name, type: n.symbol_type, file: n.file_path, line: n.start_line, raw: n },
      })),
    [visibleNodes, positions],
  )

  const initialEdges: Edge[] = useMemo(
    () =>
      visibleEdges.map((e) => {
        const color = EDGE_COLORS[e.relationship_type] ?? '#505070'
        const isCall = e.relationship_type === 'CALLS'
        const isImport = e.relationship_type === 'IMPORTS'
        return {
          id: e.relationship_id,
          source: e.source_symbol_id,
          target: e.target_symbol_id,
          type: 'smoothstep',
          animated: isCall,
          style: {
            stroke: color,
            strokeWidth: isCall ? 1.5 : 1,
            strokeDasharray: isImport ? '5 4' : undefined,
            filter: `drop-shadow(0 0 4px ${color}70)`,
          },
          markerEnd: { type: MarkerType.ArrowClosed, color, width: 11, height: 11 },
        }
      }),
    [visibleEdges],
  )

  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  useEffect(() => { setNodes(initialNodes) }, [initialNodes, setNodes])
  useEffect(() => { setEdges(initialEdges) }, [initialEdges, setEdges])

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const raw = node.data.raw as GraphNode
      selectSymbol(raw.symbol_id)
      navigateToSource(raw.file_path, raw.start_line, raw.end_line)
    },
    [selectSymbol, navigateToSource],
  )

  if (isLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 8, color: '#48485e', fontSize: 13 }}>
        <Spinner />
        Building graph…
      </div>
    )
  }

  if (error) {
    return <div style={{ padding: 16 }}><ErrorMessage message={(error as Error).message} /></div>
  }

  if (!data || data.nodes.length === 0) {
    return <EmptyState title="No graph data" description="Ingest the repository to build the dependency graph." />
  }

  // Large repo: show filter prompt before rendering anything
  if (isLarge && selectedFiles.size === 0) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          background: '#09090e',
          gap: 20,
          padding: 32,
        }}
      >
        {/* Subtle grid bg */}
        <div style={{ position: 'absolute', inset: 0, backgroundImage: 'radial-gradient(circle, #1c1c2c 1px, transparent 1px)', backgroundSize: '26px 26px', pointerEvents: 'none', opacity: 0.6 }} />

        <div style={{ position: 'relative', zIndex: 1, textAlign: 'center', maxWidth: 420 }}>
          {/* Icon */}
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
            <div style={{ width: 48, height: 48, borderRadius: 10, background: '#7b68ee14', border: '1px solid #7b68ee38', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="3" stroke="#7b68ee" strokeWidth="1.5" />
                <circle cx="20" cy="4"  r="2.5" stroke="#7b68ee" strokeWidth="1.2" opacity="0.6" />
                <circle cx="4"  cy="20" r="2.5" stroke="#7b68ee" strokeWidth="1.2" opacity="0.6" />
                <circle cx="20" cy="20" r="2.5" stroke="#4db87a" strokeWidth="1.2" opacity="0.6" />
                <line x1="12" y1="12" x2="20" y2="4"  stroke="#7b68ee" strokeWidth="1" opacity="0.4" />
                <line x1="12" y1="12" x2="4"  y2="20" stroke="#7b68ee" strokeWidth="1" opacity="0.4" />
                <line x1="12" y1="12" x2="20" y2="20" stroke="#4db87a" strokeWidth="1" opacity="0.4" />
              </svg>
            </div>
          </div>

          <div style={{ fontSize: 16, fontWeight: 600, color: '#d0d0e8', marginBottom: 8, letterSpacing: '-0.02em' }}>
            {data.nodes.length} symbols · too large to render at once
          </div>
          <div style={{ fontSize: 13, color: '#5a5a78', lineHeight: 1.6, marginBottom: 24 }}>
            Select one or more files to explore that section of the graph.
            Direct neighbors are included automatically.
          </div>

          <FileFilterPanel
            files={allFiles}
            selected={selectedFiles}
            onChange={setSelectedFiles}
          />

          <div style={{ marginTop: 12, fontSize: 11, color: '#3c3c52' }}>
            {allFiles.length} files in this repository
          </div>
        </div>
      </div>
    )
  }

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      {/* File filter toolbar — always visible when large */}
      {isLarge && (
        <div
          style={{
            position: 'absolute',
            top: 12,
            right: 16,
            zIndex: 20,
          }}
        >
          <FileFilterPanel
            files={allFiles}
            selected={selectedFiles}
            onChange={setSelectedFiles}
          />
        </div>
      )}

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        minZoom={0.08}
        maxZoom={2.5}
        style={{ background: '#09090e' }}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={26} size={1.3} color="#1c1c2c" />
        <Controls style={{ background: '#101018', border: '1px solid #23233a', borderRadius: 7 }} />
        <MiniMap
          style={{ background: '#0c0c14', border: '1px solid #23233a', borderRadius: 7 }}
          nodeColor={(n) => SYMBOL_STYLES[(n.data as { type: string }).type]?.main ?? '#6868a0'}
          maskColor="#09090eaa"
        />
      </ReactFlow>

      <Legend />
      <StatsBar
        nodeCount={visibleNodes.length}
        edgeCount={visibleEdges.length}
        visibleNodes={isLarge ? visibleNodes.length : undefined}
        totalNodes={isLarge ? data.nodes.length : undefined}
      />
    </div>
  )
}
