import { useCallback, useEffect, useRef, useState } from 'react'
import { buildWsUrl, fetchGraphTree, fetchSessionState } from '../api/client'
import type { GraphEvent, GraphTree } from '../api/types'
import { uuid } from '../utils/uuid'

const MAX_EVENTS = 20

export function useGraph(sessionId: string | null) {
  const [graphTree, setGraphTree] = useState<GraphTree | null>(null)
  const [events, setEvents] = useState<(GraphEvent & { id: string })[]>([])
  const [depth, setDepth] = useState(0)
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const questionIdRef = useRef<string | null>(null)

  const refreshTree = useCallback(async (qid: string) => {
    try {
      const tree = await fetchGraphTree(qid)
      setGraphTree(tree)
    } catch {
      // ignore
    }
  }, [])

  const pushEvent = useCallback((event: GraphEvent) => {
    setEvents((prev) => [
      { ...event, id: uuid() },
      ...prev.slice(0, MAX_EVENTS - 1),
    ])
  }, [])

  // Resolve question_id from session, then load initial graph
  useEffect(() => {
    if (!sessionId) return

    fetchSessionState(sessionId)
      .then((state) => {
        questionIdRef.current = state.question_id
        setDepth(state.depth)
        return refreshTree(state.question_id)
      })
      .catch(() => {})
  }, [sessionId, refreshTree])

  // WebSocket lifecycle
  useEffect(() => {
    if (!sessionId) {
      wsRef.current?.close()
      wsRef.current = null
      setIsConnected(false)
      return
    }

    const url = buildWsUrl(sessionId)
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => setIsConnected(true)
    ws.onclose = () => setIsConnected(false)
    ws.onerror = () => setIsConnected(false)

    ws.onmessage = (e: MessageEvent) => {
      try {
        const event = JSON.parse(e.data as string) as GraphEvent
        if (event.type === 'heartbeat') return
        pushEvent(event)

        // Refresh graph on structural changes
        if (
          event.type === 'node_created' ||
          event.type === 'position_update' ||
          event.type === 'session_created'
        ) {
          if (questionIdRef.current) refreshTree(questionIdRef.current)
          if (event.data && typeof event.data.depth === 'number') {
            setDepth(event.data.depth as number)
          }
        }
      } catch {
        // ignore malformed messages
      }
    }

    return () => {
      ws.close()
    }
  }, [sessionId, pushEvent, refreshTree])

  return { graphTree, events, depth, isConnected }
}
