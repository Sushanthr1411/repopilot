import { get, post } from './client'
import type {
  CreateRepositoryRequest,
  IndexResponse,
  IngestResponse,
  RepositoryResponse,
} from '../../types/api'

export const repositories = {
  create: (body: CreateRepositoryRequest) =>
    post<RepositoryResponse>('/repositories', body),

  get: (id: string) =>
    get<RepositoryResponse>(`/repositories/${id}`),

  ingest: (id: string) =>
    post<IngestResponse>(`/repositories/${id}/ingest`),

  index: (id: string) =>
    post<IndexResponse>(`/repositories/${id}/index`),
}
