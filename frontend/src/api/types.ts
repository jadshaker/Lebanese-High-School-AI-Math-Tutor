// ── OpenAI-compatible chat API ────────────────────────────────────────────────

export interface ChatApiMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
}

export interface ChatCompletionRequest {
  model: string
  messages: ChatApiMessage[]
  temperature?: number
  max_tokens?: number
}

export interface ChatCompletionResponse {
  id: string
  object: string
  created: number
  model: string
  choices: Array<{
    index: number
    message: ChatApiMessage
    finish_reason: string
  }>
}

// ── Health ────────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: 'healthy' | 'degraded'
  qdrant: boolean
  active_sessions: number
  uptime: number
}

// ── Graph / Sessions ──────────────────────────────────────────────────────────

export interface GraphSession {
  session_id: string
  question_id: string
  original_query: string
  depth: number
  created_at: string
}

export interface GraphSessionState {
  session_id: string
  question_id: string
  current_node_id: string
  depth: number
  is_new_branch: boolean
  original_query: string
}

export interface CytoscapeNodeData {
  id: string
  label: string
  type: 'root' | 'interaction'
  user_input?: string
  system_response?: string
}

export interface CytoscapeEdgeData {
  id: string
  source: string
  target: string
}

export interface GraphTree {
  nodes: Array<{ data: CytoscapeNodeData }>
  edges: Array<{ data: CytoscapeEdgeData }>
}

export type GraphEventType =
  | 'session_start'
  | 'session_created'
  | 'cache_search'
  | 'cache_hit'
  | 'cache_miss'
  | 'node_created'
  | 'position_update'
  | 'correction'
  | 'heartbeat'

export interface GraphEvent {
  type: GraphEventType
  session_id?: string
  data?: Record<string, unknown>
  timestamp?: string
}

// ── App-level display types ───────────────────────────────────────────────────

export interface Attachment {
  id: string
  name: string
  type: 'image' | 'text' | 'other'
  mimeType: string
  dataUrl?: string      // base64 data URL for images
  textContent?: string  // extracted text for text files
  size: number
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  isLoading?: boolean
  error?: boolean
  rating?: 'up' | 'down'
  attachments?: Attachment[]
}
