import type { AnalyzeRequest, AnalyzeResponse, ExecuteRequest, ExecuteResponse } from './types.ts'

/** The server answered, but with an error status. */
export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** FastAPI sends `detail` as a string, or as a list of validation errors (422). */
function detailMessage(body: unknown): string | undefined {
  if (typeof body !== 'object' || body === null || !('detail' in body)) return undefined
  const { detail } = body
  if (typeof detail === 'string') return detail || undefined
  if (Array.isArray(detail)) {
    const messages = detail.map((item) =>
      typeof item === 'object' && item !== null && 'msg' in item ? String(item.msg) : String(item),
    )
    return messages.join('; ') || undefined
  }
  return undefined
}

async function postJson<TResponse>(path: string, payload: unknown, fallbackError: string): Promise<TResponse> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const body: unknown = await response.json()
  if (!response.ok) throw new ApiError(detailMessage(body) ?? fallbackError, response.status)
  return body as TResponse
}

export function analyzeIssue(request: AnalyzeRequest): Promise<AnalyzeResponse> {
  return postJson('/api/pr-pilot/analyze', request, 'Analysis failed')
}

export function executeFix(request: ExecuteRequest): Promise<ExecuteResponse> {
  return postJson('/api/pr-pilot/execute', request, 'Execution failed')
}
