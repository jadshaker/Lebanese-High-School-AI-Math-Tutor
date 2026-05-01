import axios from 'axios'
import type {
  ChatApiMessage,
  ChatCompletionResponse,
  GraphSession,
  GraphSessionState,
  GraphTree,
  HealthResponse,
} from './types'

const http = axios.create({ timeout: 90_000 })

export async function sendChatMessage(messages: ChatApiMessage[]): Promise<string> {
  const { data } = await http.post<ChatCompletionResponse>('/v1/chat/completions', {
    model: 'math-tutor',
    messages,
    temperature: 0.7,
  })
  return data.choices[0]?.message?.content ?? ''
}

export async function fetchHealth(): Promise<HealthResponse> {
  const { data } = await http.get<HealthResponse>('/health')
  return data
}

export async function fetchSessions(): Promise<GraphSession[]> {
  const { data } = await http.get<GraphSession[]>('/graph/sessions')
  return data
}

export async function fetchSessionState(sessionId: string): Promise<GraphSessionState> {
  const { data } = await http.get<GraphSessionState>(`/graph/session/${sessionId}`)
  return data
}

export async function fetchGraphTree(questionId: string): Promise<GraphTree> {
  const { data } = await http.get<GraphTree>(`/graph/tree/${questionId}`)
  return data
}

/** Build a WebSocket URL that works in both dev (Vite proxy) and production (nginx proxy). */
export function buildWsUrl(sessionId: string): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}/graph/ws/${sessionId}`
}
