import { get } from './client'
import type { DependencyResponse, GraphResponse } from '../../types/api'

export const graph = {
  get: (repoId: string) =>
    get<GraphResponse>(`/repositories/${repoId}/graph`),

  dependencies: (repoId: string, symbolId: string) =>
    get<DependencyResponse[]>(`/repositories/${repoId}/symbols/${symbolId}/dependencies`),

  dependents: (repoId: string, symbolId: string) =>
    get<DependencyResponse[]>(`/repositories/${repoId}/symbols/${symbolId}/dependents`),

  callers: (repoId: string, symbolId: string) =>
    get<DependencyResponse[]>(`/repositories/${repoId}/symbols/${symbolId}/callers`),

  callees: (repoId: string, symbolId: string) =>
    get<DependencyResponse[]>(`/repositories/${repoId}/symbols/${symbolId}/callees`),
}
