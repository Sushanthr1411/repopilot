import { createContext, useContext, useState, useMemo, type ReactNode } from 'react'
import type { FileSummary } from '../../types/api'

export type LeftTab = 'files' | 'symbols' | 'search'
export type ViewMode = 'code' | 'graph'

interface LineRange {
  start: number
  end: number
}

interface WorkspaceState {
  repoId: string
  // Left panel
  leftTab: LeftTab
  setLeftTab: (t: LeftTab) => void
  leftCollapsed: boolean
  setLeftCollapsed: (v: boolean) => void
  // Right panel
  rightCollapsed: boolean
  setRightCollapsed: (v: boolean) => void
  // Center view
  viewMode: ViewMode
  setViewMode: (m: ViewMode) => void
  // File / code selection
  selectedFileId: string | null
  lineRange: LineRange | null
  filesByPath: Record<string, FileSummary>
  setFilesByPath: (m: Record<string, FileSummary>) => void
  navigateToSource: (filePath: string, startLine?: number, endLine?: number) => void
  // Symbol
  selectedSymbolId: string | null
  selectSymbol: (id: string | null) => void
}

const WorkspaceCtx = createContext<WorkspaceState | null>(null)

export function WorkspaceProvider({
  repoId,
  children,
}: {
  repoId: string
  children: ReactNode
}) {
  const [leftTab, setLeftTab] = useState<LeftTab>('files')
  const [leftCollapsed, setLeftCollapsed] = useState(false)
  const [rightCollapsed, setRightCollapsed] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('code')
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null)
  const [lineRange, setLineRange] = useState<LineRange | null>(null)
  const [filesByPath, setFilesByPath] = useState<Record<string, FileSummary>>({})
  const [selectedSymbolId, selectSymbol] = useState<string | null>(null)

  function navigateToSource(filePath: string, startLine?: number, endLine?: number) {
    const file = filesByPath[filePath]
    if (file) {
      setSelectedFileId(file.id)
      setLineRange(
        startLine !== undefined
          ? { start: startLine, end: endLine ?? startLine }
          : null,
      )
      setViewMode('code')
    }
  }

  const value = useMemo<WorkspaceState>(
    () => ({
      repoId,
      leftTab, setLeftTab,
      leftCollapsed, setLeftCollapsed,
      rightCollapsed, setRightCollapsed,
      viewMode, setViewMode,
      selectedFileId,
      lineRange,
      filesByPath,
      setFilesByPath,
      navigateToSource,
      selectedSymbolId,
      selectSymbol,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [repoId, leftTab, leftCollapsed, rightCollapsed, viewMode, selectedFileId, lineRange, filesByPath, selectedSymbolId],
  )

  return <WorkspaceCtx.Provider value={value}>{children}</WorkspaceCtx.Provider>
}

export function useWorkspace() {
  const ctx = useContext(WorkspaceCtx)
  if (!ctx) throw new Error('useWorkspace must be used inside WorkspaceProvider')
  return ctx
}
