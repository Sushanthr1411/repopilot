const BASE = '/api/v1'

export class ApiResponseError extends Error {
  status: number
  code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiResponseError'
    this.status = status
    this.code = code
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let code = 'UNKNOWN_ERROR'
    let message = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (body?.detail?.code) {
        code = body.detail.code
        message = body.detail.message ?? message
      } else if (typeof body?.detail === 'string') {
        message = body.detail
      }
    } catch {
      // ignore parse errors
    }
    throw new ApiResponseError(res.status, code, message)
  }
  if (res.status === 204) return undefined as unknown as T
  return res.json() as Promise<T>
}

export async function get<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const url = new URL(`${BASE}${path}`, window.location.origin)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      url.searchParams.set(k, String(v))
    }
  }
  const res = await fetch(url.toString())
  return handleResponse<T>(res)
}

export async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  return handleResponse<T>(res)
}
