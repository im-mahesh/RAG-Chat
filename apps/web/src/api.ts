import type { components } from 'api-client'
import { createSseParser } from './sse.ts'

type Schemas = components['schemas']

export type DocumentInfo = Schemas['DocumentInfo']
export type UploadResponse = Schemas['UploadResponse']
export type DeleteResponse = Schemas['DeleteResponse']
export type Chunk = Schemas['Chunk']
export type ChatRequest = Schemas['ChatRequest']
export type HistoryMessage = Schemas['HistoryMessage']
export type HealthResponse = Schemas['HealthResponse']
export type StreamEvent = Schemas['StreamEvent']

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail) && body.detail[0]?.msg) {
      return `Invalid request: ${body.detail[0].msg}`
    }
  } catch {
    // Not JSON; fall through to the generic message.
  }
  return `Request failed (${response.status}).`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, init)
  } catch {
    throw new ApiError(`Cannot reach the API at ${API_URL}. Is it running?`, 0)
  }
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status)
  }
  return response.json()
}

export function fetchHealth(): Promise<HealthResponse> {
  return request('/health')
}

export function listDocuments(): Promise<DocumentInfo[]> {
  return request('/documents')
}

export function uploadDocument(file: File): Promise<UploadResponse> {
  const body = new FormData()
  body.append('file', file)
  return request('/documents', { method: 'POST', body })
}

export function deleteDocument(id: string): Promise<DeleteResponse> {
  return request(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

function parseEvent(data: string): StreamEvent {
  try {
    return JSON.parse(data) as StreamEvent
  } catch {
    throw new ApiError('Received a malformed event from the server.', 0)
  }
}

async function openStream(payload: ChatRequest, signal: AbortSignal): Promise<Response> {
  let response: Response
  try {
    response = await fetch(`${API_URL}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    })
  } catch (error) {
    if (signal.aborted) throw error
    throw new ApiError(`Cannot reach the API at ${API_URL}. Is it running?`, 0)
  }
  if (!response.ok) throw new ApiError(await errorMessage(response), response.status)
  if (!response.body) throw new ApiError('The server sent no response body.', response.status)
  return response
}

/**
 * Streams an answer from POST /chat/stream, calling `onEvent` for each event.
 *
 * Resolves after a `done` or `error` event. Rejects with an ApiError for HTTP
 * failures or if the connection closes early, and with the browser's AbortError
 * when `signal` is aborted.
 */
export async function streamChat(
  payload: ChatRequest,
  signal: AbortSignal,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const response = await openStream(payload, signal)
  const reader = response.body!.getReader()
  let finished = false
  const parser = createSseParser((data) => {
    const event = parseEvent(data)
    finished ||= event.type === 'done' || event.type === 'error'
    onEvent(event)
  })
  while (!finished) {
    const { done, value } = await reader.read()
    if (done) break
    parser.push(value)
  }
  if (!finished) parser.end()
  if (!finished) throw new ApiError('The connection closed before the answer was complete.', 0)
  await reader.cancel()
}
