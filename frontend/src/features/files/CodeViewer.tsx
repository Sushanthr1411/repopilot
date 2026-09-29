import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import Editor, { type Monaco } from '@monaco-editor/react'
import type { editor as MonacoEditor } from 'monaco-editor'
import { files as filesApi } from '../../services/api/files'
import { useWorkspace } from '../workspace/WorkspaceContext'
import { Spinner } from '../../components/ui/Spinner'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorMessage } from '../../components/ui/ErrorMessage'

function languageFromPath(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase()
  const map: Record<string, string> = {
    py: 'python', ts: 'typescript', tsx: 'typescript',
    js: 'javascript', jsx: 'javascript', json: 'json',
    md: 'markdown', yaml: 'yaml', yml: 'yaml',
    toml: 'toml', sh: 'shell', bash: 'shell',
    css: 'css', html: 'html', sql: 'sql', rs: 'rust',
    go: 'go', java: 'java', rb: 'ruby', cpp: 'cpp', c: 'c',
  }
  return map[ext ?? ''] ?? 'plaintext'
}

function defineRepoPilotTheme(monaco: Monaco) {
  monaco.editor.defineTheme('repopilot', {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: 'comment', foreground: '555570', fontStyle: 'italic' },
      { token: 'keyword', foreground: '7c6af7' },
      { token: 'string', foreground: '8bc34a' },
      { token: 'number', foreground: 'f0a070' },
      { token: 'type', foreground: '64b5f6' },
      { token: 'class', foreground: '64b5f6' },
    ],
    colors: {
      'editor.background': '#0e0e12',
      'editor.foreground': '#d4d4e8',
      'editorLineNumber.foreground': '#404058',
      'editorLineNumber.activeForeground': '#6060a0',
      'editor.lineHighlightBackground': '#1a1a26',
      'editor.selectionBackground': '#2a2a5a',
      'editorCursor.foreground': '#7c6af7',
      'editorIndentGuide.background1': '#2a2a36',
      'editorIndentGuide.activeBackground1': '#4a4a60',
      'scrollbarSlider.background': '#2a2a3666',
      'scrollbarSlider.hoverBackground': '#3a3a5066',
      'editorWidget.background': '#141418',
      'editorWidget.border': '#2a2a36',
    },
  })
}

export function CodeViewer() {
  const { repoId, selectedFileId, lineRange, filesByPath } = useWorkspace()
  const editorRef = useRef<MonacoEditor.IStandaloneCodeEditor | null>(null)
  const decorationsRef = useRef<string[]>([])

  const selectedFile = selectedFileId
    ? Object.values(filesByPath).find((f) => f.id === selectedFileId)
    : null

  const { data, isLoading, error } = useQuery({
    queryKey: ['file-content', repoId, selectedFileId],
    queryFn: () => filesApi.get(repoId, selectedFileId!),
    enabled: !!selectedFileId,
  })

  // Navigate to line range when it changes
  useEffect(() => {
    const editor = editorRef.current
    if (!editor || !lineRange) return

    // Slight delay to ensure content is loaded
    const id = setTimeout(() => {
      editor.revealLineInCenter(lineRange.start, 0)
      const newDecorations = editor.createDecorationsCollection([
        {
          range: {
            startLineNumber: lineRange.start,
            startColumn: 1,
            endLineNumber: lineRange.end,
            endColumn: 1,
          },
          options: {
            isWholeLine: true,
            className: 'source-highlight',
            linesDecorationsClassName: 'source-highlight-gutter',
          },
        },
      ])
      decorationsRef.current = newDecorations.getRanges().map((r) => r.toString())
    }, 100)

    return () => clearTimeout(id)
  }, [lineRange, data])

  function handleEditorMount(editor: MonacoEditor.IStandaloneCodeEditor, monaco: Monaco) {
    editorRef.current = editor
    defineRepoPilotTheme(monaco)
    monaco.editor.setTheme('repopilot')

    // Inject highlight style
    const styleId = 'repopilot-highlight'
    if (!document.getElementById(styleId)) {
      const style = document.createElement('style')
      style.id = styleId
      style.textContent = `
        .source-highlight { background: color-mix(in srgb, #7c6af7 10%, transparent) !important; }
        .source-highlight-gutter { background: #7c6af7; width: 2px !important; margin-left: 3px; }
      `
      document.head.appendChild(style)
    }
  }

  if (!selectedFileId) {
    return (
      <EmptyState
        title="No file selected"
        description="Select a file from the explorer, or click a source reference in the AI assistant."
      />
    )
  }

  if (isLoading) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          color: 'var(--color-text-3)',
          gap: 8,
        }}
      >
        <Spinner />
        Loading…
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ padding: 16 }}>
        <ErrorMessage message={(error as Error).message} />
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* File path header */}
      <div
        style={{
          padding: '6px 14px',
          borderBottom: '1px solid var(--color-border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
          background: 'var(--color-surface)',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--color-text-2)',
          }}
        >
          {selectedFile?.path ?? ''}
        </span>
        {lineRange && (
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: 'var(--color-accent)',
            }}
          >
            :{lineRange.start}–{lineRange.end}
          </span>
        )}
      </div>

      {/* Editor */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <Editor
          height="100%"
          language={languageFromPath(selectedFile?.path ?? '')}
          value={data?.content ?? ''}
          theme="repopilot"
          options={{
            readOnly: true,
            fontSize: 12,
            fontFamily: '"JetBrains Mono", "Fira Code", Consolas, monospace',
            fontLigatures: true,
            lineNumbers: 'on',
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            wordWrap: 'off',
            padding: { top: 8 },
            renderLineHighlight: 'line',
            smoothScrolling: true,
            cursorBlinking: 'smooth',
            folding: true,
            bracketPairColorization: { enabled: true },
          }}
          onMount={handleEditorMount}
          loading={
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                height: '100%',
                color: 'var(--color-text-3)',
                gap: 8,
                background: '#0e0e12',
              }}
            >
              <Spinner />
            </div>
          }
        />
      </div>
    </div>
  )
}
