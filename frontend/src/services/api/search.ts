import { post } from './client'
import type { SearchRequest, SearchResponse } from '../../types/api'

export const search = {
  query: (repoId: string, body: SearchRequest) =>
    post<SearchResponse>(`/repositories/${repoId}/search`, body),
}
