import type {
  AddKnowledgeResponse,
  ChatResponse,
  CreateSessionResponse,
  KnowledgeResponse,
  Message,
  Metrics,
  Order,
  Product,
  SearchResponse,
  Session,
  StatusResponse,
  TracesResponse,
} from './types'

const API_PREFIX = '/api/demo'

export class ApiError extends Error {
  status: number
  constructor(message: string, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_PREFIX}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch {
    throw new ApiError('无法连接演示服务，请确认后端已在 8765 端口运行。')
  }

  const contentType = response.headers.get('content-type') ?? ''
  const payload = response.status === 204 ? null : contentType.includes('application/json')
    ? await response.json() as unknown
    : await response.text()
  if (!response.ok) {
    const detail = typeof payload === 'object' && payload !== null
      ? (payload as { detail?: string; message?: string }).detail ?? (payload as { message?: string }).message
      : undefined
    throw new ApiError(detail || `请求失败（${response.status}）`, response.status)
  }
  return payload as T
}

const json = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })

export const api = {
  getStatus: () => request<StatusResponse>('/status'),
  getSessions: () => request<{ sessions: Session[] }>('/sessions'),
  createSession: () => request<CreateSessionResponse>('/sessions', json({})),
  getMessages: (sessionId: string) => request<{ messages: Message[] }>(`/sessions/${encodeURIComponent(sessionId)}/messages`),
  chat: (sessionId: string, content: string) => request<ChatResponse>('/chat', json({ session_id: sessionId, content })),
  confirmAction: (actionId: string) => request<{ message: string; action: import('./types').Action; order: Order }>(`/actions/${encodeURIComponent(actionId)}/confirm`, json({})),
  deleteSession: (sessionId: string) => request<void>(`/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' }),
  getKnowledge: () => request<KnowledgeResponse>('/knowledge'),
  addKnowledge: (body: { title: string; content: string; category: string; source?: string }) => request<AddKnowledgeResponse>('/knowledge', json(body)),
  deleteKnowledge: (id: string) => request<{ deleted: boolean }>(`/knowledge/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  search: (query: string, domains: string[] = [], top_k = 8) => request<import('./types').SearchResponse>('/search', json({ query, domains, top_k })),
  getOrders: () => request<{ orders: Order[] }>('/orders'),
  getProducts: () => request<{ products: Product[] }>('/products'),
  getTraces: () => request<TracesResponse>('/traces'),
  getMetrics: () => request<Metrics>('/metrics'),
}
