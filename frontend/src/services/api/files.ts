import { get } from './client'
import type { FileContent, FileListResponse } from '../../types/api'

export const files = {
  list: (repoId: string, params?: { limit?: number; offset?: number }) =>
    get<FileListResponse>(`/repositories/${repoId}/files`, {
      limit: params?.limit ?? 500,
      offset: params?.offset ?? 0,
    }),

  get: (repoId: string, fileId: string, opts?: { start_line?: number; end_line?: number }) =>
    get<FileContent>(`/repositories/${repoId}/files/${fileId}`, opts as Record<string, number>),
}
