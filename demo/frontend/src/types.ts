export type Role = 'user' | 'assistant'
export type ActionType = 'cancel_order' | 'refund_request'
export type ActionStatus = 'pending' | 'confirmed'
export type StepStatus = 'ok' | 'fallback' | 'blocked'

export interface StatusResponse {
  mode: 'demo' | string
  intent_provider: 'local_rules' | 'jev' | string
  embedding_provider: string
  llm_provider: 'template' | 'openai' | string
  jev_configured: boolean
  llm_configured: boolean
  documents: number
  orders: number
  products: number
  features: string[]
  warning: string
}

export interface Session {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
  status: string
}

export interface Citation {
  id: string
  title: string
  content: string
  category: string
  source: string
  version: string
  score: number
  dense_score: number
  bm25_score: number
}

export interface Action {
  id: string
  type: ActionType
  order_no: string
  status: ActionStatus
  label: string
}

export interface TraceStep {
  name: string
  status: StepStatus
  duration_ms: number
  details: unknown
}

export interface Decision {
  intent: string
  domains: string[]
  confidence: number
  provider: string
  need_human: boolean
  multi_intent: boolean
}

export interface Trace {
  id: string
  session_id: string
  created_at: string
  duration_ms: number
  steps: TraceStep[]
  decision: Decision
  route: string
}

export interface Message {
  id: string
  session_id: string
  role: Role
  content: string
  created_at: string
  trace?: Trace
  citations?: Citation[]
  actions?: Action[]
}

export interface CreateSessionResponse {
  session: Session
  welcome_message: string
  quick_replies: string[]
}

export interface ChatResponse {
  message: Message
  decision: Decision
  trace: Trace
  citations: Citation[]
  actions: Action[]
  quick_replies: string[]
}

export interface KnowledgeDocument {
  id: string
  title: string
  content: string
  category: string
  source: string
  version: string
  updated_at: string
}

export interface KnowledgeResponse {
  documents: KnowledgeDocument[]
  categories: string[]
}

export interface AddKnowledgeResponse {
  document: KnowledgeDocument
  count: number
}

export interface SearchResponse {
  results: Citation[]
  strategy: string
  embedding_provider: string
  duration_ms: number
}

export interface Order {
  order_no: string
  product_name: string
  sku: string
  status: string
  status_label: string
  quantity: number
  total_amount: number
  tracking_no: string
  updated_at: string
}

export interface Product {
  sku: string
  name: string
  category: string
  price: number
  stock: number
  description: string
}

export interface TracesResponse {
  traces: Trace[]
}

export interface Metrics {
  sessions: number
  messages: number
  documents: number
  orders: number
  traces: number
}

export interface ApiErrorPayload {
  detail?: string
  message?: string
}
