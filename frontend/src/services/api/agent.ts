import { post } from './client'
import type { AskRequest, AskResponse } from '../../types/api'

export const agent = {
  ask: (repoId: string, body: AskRequest) =>
    post<AskResponse>(`/repositories/${repoId}/ask`, body),
}
