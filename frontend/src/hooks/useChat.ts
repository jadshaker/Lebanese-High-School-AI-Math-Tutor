import { useCallback, useState } from 'react'
import { fetchSessions, sendChatMessage } from '../api/client'
import type { ChatApiMessage, Message } from '../api/types'
import { uuid } from '../utils/uuid'

const LOADING_ID = '__loading__'

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [apiHistory, setApiHistory] = useState<ChatApiMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [firstQuery, setFirstQuery] = useState<string | null>(null)

  const resolveSession = useCallback(
    async (query: string) => {
      // Retry up to 4 times with increasing delays to find the session
      for (const delay of [800, 1500, 2500, 4000]) {
        await new Promise((r) => setTimeout(r, delay))
        try {
          const sessions = await fetchSessions()
          if (!sessions.length) continue
          const match =
            sessions.find((s) =>
              s.original_query.toLowerCase().includes(query.toLowerCase().slice(0, 40)),
            ) ?? sessions[sessions.length - 1]
          if (match) {
            setSessionId(match.session_id)
            return
          }
        } catch {
          // silently retry
        }
      }
    },
    [],
  )

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || isLoading) return

      const userMsg: Message = {
        id: uuid(),
        role: 'user',
        content: text.trim(),
        timestamp: new Date(),
      }
      const loadingMsg: Message = {
        id: LOADING_ID,
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        isLoading: true,
      }

      setMessages((prev) => [...prev, userMsg, loadingMsg])
      setIsLoading(true)

      const newHistory: ChatApiMessage[] = [...apiHistory, { role: 'user', content: text.trim() }]

      try {
        const reply = await sendChatMessage(newHistory)

        const assistantMsg: Message = {
          id: uuid(),
          role: 'assistant',
          content: reply,
          timestamp: new Date(),
        }

        setMessages((prev) => prev.filter((m) => m.id !== LOADING_ID).concat(assistantMsg))
        setApiHistory([...newHistory, { role: 'assistant', content: reply }])

        // Kick off session resolution once (first message only)
        if (!firstQuery && !sessionId) {
          setFirstQuery(text.trim())
          resolveSession(text.trim())
        }
      } catch {
        const errorMsg: Message = {
          id: uuid(),
          role: 'assistant',
          content: 'Something went wrong connecting to the tutor. Please try again.',
          timestamp: new Date(),
          error: true,
        }
        setMessages((prev) => prev.filter((m) => m.id !== LOADING_ID).concat(errorMsg))
      } finally {
        setIsLoading(false)
      }
    },
    [isLoading, apiHistory, firstQuery, sessionId, resolveSession],
  )

  const clearChat = useCallback(() => {
    setMessages([])
    setApiHistory([])
    setSessionId(null)
    setFirstQuery(null)
    setIsLoading(false)
  }, [])

  return { messages, isLoading, sessionId, sendMessage, clearChat }
}
