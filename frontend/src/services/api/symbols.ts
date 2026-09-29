import { get } from './client'
import type { SymbolListResponse, SymbolResponse } from '../../types/api'

export const symbols = {
  list: (
    repoId: string,
    params?: { limit?: number; offset?: number; symbol_type?: string; name?: string },
  ) =>
    get<SymbolListResponse>(`/repositories/${repoId}/symbols`, {
      limit: params?.limit ?? 500,
      offset: params?.offset ?? 0,
      ...(params?.symbol_type ? { symbol_type: params.symbol_type } : {}),
      ...(params?.name ? { name: params.name } : {}),
    } as Record<string, string | number>),

  get: (repoId: string, symbolId: string) =>
    get<SymbolResponse>(`/repositories/${repoId}/symbols/${symbolId}`),
}
