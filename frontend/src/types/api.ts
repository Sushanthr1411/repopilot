// Types mirroring the backend Pydantic schemas.
// Keep in sync with backend/app/schemas/*.py

export interface RepositoryResponse {
  id: string
  name: string
  source_url: string | null
  local_path: string | null
  status: 'pending' | 'ready' | 'error' | string
  created_at: string
  updated_at: string
  file_count: number
  symbol_count: number
}

export interface CreateRepositoryRequest {
  name: string
  local_path: string
  source_url?: string
}

export interface IngestResponse {
  repository_id: string
  status: string
  total_files: number
  parsed_files: number
  files_with_errors: number
  total_symbols: number
  total_relationships: number
  unresolved_relationships: number
  parse_errors: string[]
  warnings: string[]
}

export interface IndexResponse {
  repository_id: string
  total_files: number
  chunks_created: number
  chunks_deleted: number
  files_skipped: number
}

// Files
export interface FileSummary {
  id: string
  repository_id: string
  path: string
  language: string | null
  size: number | null
  content_hash: string | null
  created_at: string
  updated_at: string
}

export interface FileContent extends FileSummary {
  content: string
  total_lines: number
}

export interface FileListResponse {
  items: FileSummary[]
  total: number
  limit: number
  offset: number
}

// Symbols
export interface SymbolResponse {
  id: string
  file_id: string
  file_path: string
  name: string
  qualified_name: string
  symbol_type: 'module' | 'class' | 'function' | 'async_function' | 'method' | string
  start_line: number
  end_line: number
  signature: string | null
  docstring: string | null
  created_at: string
  updated_at: string
}

export interface SymbolListResponse {
  items: SymbolResponse[]
  total: number
  limit: number
  offset: number
}

// Graph
export interface GraphNode {
  symbol_id: string
  name: string
  qualified_name: string
  symbol_type: string
  file_id: string
  file_path: string
  start_line: number
  end_line: number
}

export interface GraphEdge {
  relationship_id: string
  source_symbol_id: string
  target_symbol_id: string
  relationship_type: 'CALLS' | 'IMPORTS' | 'DEFINES' | 'INHERITS' | 'USES' | string
  confidence: number | null
}

export interface GraphResponse {
  repository_id: string
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface DependencyResponse {
  symbol_id: string
  name: string
  qualified_name: string
  symbol_type: string
  file_path: string
  start_line: number
  end_line: number
}

// Search
export interface SearchRequest {
  query: string
  top_k?: number
}

export interface SearchResultItem {
  chunk_id: string
  file_id: string
  file_path: string
  start_line: number
  end_line: number
  content: string
  symbol_id: string | null
  symbol_name: string | null
  qualified_name: string | null
  distance: number
}

export interface SearchResponse {
  query: string
  results: SearchResultItem[]
}

// Agent
export interface AskRequest {
  question: string
}

export interface AgentToolEvent {
  tool_name: string
  arguments_summary: string
  success: boolean
  duration_ms: number
}

export interface AgentSource {
  file_path: string
  start_line: number | null
  end_line: number | null
  symbol: string | null
}

export interface AskResponse {
  answer: string
  sources: AgentSource[]
  tools_used: AgentToolEvent[]
  iterations: number
  truncated: boolean
  model: string | null
}

// API error
export interface ApiError {
  code: string
  message: string
}
