import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchSessions, sendChatMessage } from '../api/client'
import type { Attachment, ChatApiMessage, Message } from '../api/types'
import { uuid } from '../utils/uuid'

/** Build the text sent to the API, appending attachment context the backend can use. */
function buildApiText(text: string, attachments?: Attachment[]): string {
  if (!attachments || attachments.length === 0) return text
  const parts: string[] = text ? [text] : []
  for (const a of attachments) {
    if (a.type === 'image') {
      parts.push(`[Student attached an image: ${a.name}]`)
    } else if (a.type === 'text' && a.textContent) {
      parts.push(`--- Attached file: ${a.name} ---\n${a.textContent.slice(0, 4000)}`)
    } else {
      parts.push(`[Student attached a file: ${a.name}]`)
    }
  }
  return parts.join('\n\n')
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Conversation {
  id: string
  title: string
  messages: Message[]
  apiHistory: ChatApiMessage[]
  sessionId: string | null
  isPinned: boolean
  createdAt: string
  updatedAt: string
}

// ── Storage helpers ───────────────────────────────────────────────────────────

const STORAGE_KEY = 'math-atelier-convs-v1'
const ACTIVE_KEY = 'math-atelier-active-v1'
const LOADING_ID = '__loading__'

function persist(convs: Conversation[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(convs))
  } catch {
    // quota exceeded: trim oldest non-pinned
    const trimmed = convs.filter((c) => c.isPinned).concat(convs.filter((c) => !c.isPinned).slice(0, 50))
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed)) } catch { /* */ }
  }
}

function load(): Conversation[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as Conversation[]
    return parsed.map((c) => ({
      ...c,
      messages: c.messages.map((m) => ({ ...m, timestamp: new Date(m.timestamp) })),
    }))
  } catch {
    return []
  }
}

/** Rebuild the OpenAI-format history from displayed messages (source of truth). */
function toApiHistory(messages: Message[]): ChatApiMessage[] {
  return messages
    .filter((m) => !m.isLoading && !m.error && m.content.trim())
    .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content }))
}

function autoTitle(text: string) {
  return text.slice(0, 52) + (text.length > 52 ? '…' : '')
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useConversationStore() {
  const [conversations, setConversations] = useState<Conversation[]>(load)
  const [activeId, setActiveIdState] = useState<string | null>(
    () => localStorage.getItem(ACTIVE_KEY) ?? load()[0]?.id ?? null,
  )
  const [isLoading, setIsLoading] = useState(false)

  // Refs for async callbacks (avoid stale closures)
  const convRef = useRef(conversations)
  const activeIdRef = useRef(activeId)
  const isLoadingRef = useRef(isLoading)

  useEffect(() => { convRef.current = conversations }, [conversations])
  useEffect(() => { activeIdRef.current = activeId }, [activeId])
  useEffect(() => { isLoadingRef.current = isLoading }, [isLoading])

  // Persist on change
  useEffect(() => { persist(conversations) }, [conversations])
  useEffect(() => {
    if (activeId) localStorage.setItem(ACTIVE_KEY, activeId)
    else localStorage.removeItem(ACTIVE_KEY)
  }, [activeId])

  // ── Derived ──────────────────────────────────────────────────────────────────

  const activeConversation = conversations.find((c) => c.id === activeId) ?? null

  // ── CRUD ─────────────────────────────────────────────────────────────────────

  const patch = useCallback((id: string, update: Partial<Conversation>) => {
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? { ...c, ...update, updatedAt: new Date().toISOString() } : c)),
    )
  }, [])

  const setActiveId = useCallback((id: string | null) => {
    setActiveIdState(id)
    setIsLoading(false)
  }, [])

  const createConversation = useCallback((): string => {
    const id = uuid()
    const now = new Date().toISOString()
    const conv: Conversation = {
      id, title: 'New Conversation', messages: [],
      apiHistory: [], sessionId: null, isPinned: false,
      createdAt: now, updatedAt: now,
    }
    setConversations((prev) => [conv, ...prev])
    setActiveIdState(id)
    setIsLoading(false)
    return id
  }, [])

  const deleteConversation = useCallback((id: string) => {
    setConversations((prev) => prev.filter((c) => c.id !== id))
    setActiveIdState((prev) => {
      if (prev !== id) return prev
      const remaining = convRef.current.filter((c) => c.id !== id)
      return remaining[0]?.id ?? null
    })
  }, [])

  const deleteAll = useCallback(() => {
    setConversations([])
    setActiveIdState(null)
  }, [])

  const renameConversation = useCallback((id: string, title: string) => {
    patch(id, { title: title.trim() || 'Untitled' })
  }, [patch])

  const togglePin = useCallback((id: string) => {
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? { ...c, isPinned: !c.isPinned, updatedAt: new Date().toISOString() } : c)),
    )
  }, [])

  // ── Import / Export ───────────────────────────────────────────────────────────

  const exportAll = useCallback(() => {
    const data = JSON.stringify(convRef.current, null, 2)
    const blob = new Blob([data], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `math-atelier-export-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }, [])

  const importConversations = useCallback((file: File) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        const parsed = JSON.parse(e.target?.result as string) as Conversation[]
        const rehydrated = parsed.map((c) => ({
          ...c,
          messages: c.messages.map((m) => ({ ...m, timestamp: new Date(m.timestamp) })),
        }))
        setConversations((prev) => {
          const existing = new Set(prev.map((c) => c.id))
          const merged = [...prev, ...rehydrated.filter((c) => !existing.has(c.id))]
          return merged
        })
      } catch { /* invalid file */ }
    }
    reader.readAsText(file)
  }, [])

  // ── Session resolution ────────────────────────────────────────────────────────

  const resolveSession = useCallback(async (convId: string, query: string) => {
    for (const delay of [900, 1800, 3000, 5000]) {
      await new Promise((r) => setTimeout(r, delay))
      try {
        const sessions = await fetchSessions()
        if (!sessions.length) continue
        const match =
          sessions.find((s) =>
            s.original_query.toLowerCase().includes(query.toLowerCase().slice(0, 40)),
          ) ?? sessions[sessions.length - 1]
        if (match) {
          patch(convId, { sessionId: match.session_id })
          return
        }
      } catch { /* retry */ }
    }
  }, [patch])

  // ── Core send ─────────────────────────────────────────────────────────────────

  /**
   * Send `text` on behalf of `convId`, given the messages already displayed
   * (without the loading bubble) and the trimmed API history.
   */
  const _send = useCallback(async (
    convId: string,
    text: string,
    baseMessages: Message[],
    baseHistory: ChatApiMessage[],
    attachments?: Attachment[],
  ) => {
    const isFirst = baseMessages.length === 0

    const userMsg: Message = {
      id: uuid(), role: 'user',
      content: text.trim(), timestamp: new Date(),
      attachments,
    }
    const loadingMsg: Message = {
      id: LOADING_ID, role: 'assistant',
      content: '', timestamp: new Date(), isLoading: true,
    }

    setConversations((prev) =>
      prev.map((c) =>
        c.id === convId
          ? { ...c, messages: [...baseMessages, userMsg, loadingMsg], updatedAt: new Date().toISOString() }
          : c,
      ),
    )
    setIsLoading(true)

    // API sees enriched text (attachment context appended); display shows original text only
    const apiText = buildApiText(text.trim(), attachments)
    const newHistory: ChatApiMessage[] = [...baseHistory, { role: 'user', content: apiText }]

    try {
      const reply = await sendChatMessage(newHistory)

      const assistantMsg: Message = {
        id: uuid(), role: 'assistant',
        content: reply, timestamp: new Date(),
      }
      const finalMessages = [...baseMessages, userMsg, assistantMsg]
      // Build apiHistory from enriched history (keeps attachment context for future turns)
      const finalHistory: ChatApiMessage[] = [...newHistory, { role: 'assistant', content: reply }]

      patch(convId, {
        messages: finalMessages,
        apiHistory: finalHistory,
        ...(isFirst ? { title: autoTitle(text.trim() || attachments?.[0]?.name || 'Attachment') } : {}),
      })

      if (isFirst) resolveSession(convId, text.trim())
    } catch {
      const errMsg: Message = {
        id: uuid(), role: 'assistant',
        content: 'Could not reach the tutor. Please check the backend is running and try again.',
        timestamp: new Date(), error: true,
      }
      setConversations((prev) =>
        prev.map((c) =>
          c.id === convId
            ? { ...c, messages: [...baseMessages, userMsg, errMsg], updatedAt: new Date().toISOString() }
            : c,
        ),
      )
    } finally {
      setIsLoading(false)
    }
  }, [patch, resolveSession])

  // ── Public message operations ─────────────────────────────────────────────────

  const sendMessage = useCallback(async (text: string, attachments?: Attachment[]) => {
    if ((!text.trim() && !attachments?.length) || isLoadingRef.current) return
    let convId = activeIdRef.current
    if (!convId) convId = createConversation()
    const conv = convRef.current.find((c) => c.id === convId)
    const clean = (conv?.messages ?? []).filter((m) => !m.isLoading)
    await _send(convId, text.trim(), clean, toApiHistory(clean), attachments)
  }, [createConversation, _send])

  const regenerate = useCallback(async () => {
    if (isLoadingRef.current) return
    const conv = convRef.current.find((c) => c.id === activeIdRef.current)
    if (!conv) return
    const msgs = conv.messages.filter((m) => !m.isLoading)

    // Remove the last assistant message
    const lastAiIdx = msgs.reduceRight((acc, m, i) => (acc === -1 && m.role === 'assistant' ? i : acc), -1)
    if (lastAiIdx === -1) return

    const trimmed = msgs.slice(0, lastAiIdx)
    const lastUser = [...trimmed].reverse().find((m) => m.role === 'user')
    if (!lastUser) return

    patch(conv.id, { messages: trimmed, apiHistory: toApiHistory(trimmed) })
    await _send(conv.id, lastUser.content, trimmed, toApiHistory(trimmed))
  }, [_send, patch])

  const editAndResend = useCallback(async (messageId: string, newText: string) => {
    if (isLoadingRef.current || !newText.trim()) return
    const conv = convRef.current.find((c) => c.id === activeIdRef.current)
    if (!conv) return
    const msgs = conv.messages.filter((m) => !m.isLoading)

    const idx = msgs.findIndex((m) => m.id === messageId)
    if (idx === -1) return

    const prior = msgs.slice(0, idx) // everything before the edited message
    patch(conv.id, { messages: prior, apiHistory: toApiHistory(prior) })
    await _send(conv.id, newText.trim(), prior, toApiHistory(prior))
  }, [_send, patch])

  const rateMessage = useCallback((messageId: string, rating: 'up' | 'down') => {
    if (!activeIdRef.current) return
    patch(activeIdRef.current, {
      messages: convRef.current
        .find((c) => c.id === activeIdRef.current)
        ?.messages.map((m) => (m.id === messageId ? { ...m, rating } : m)) ?? [],
    })
  }, [patch])

  return {
    conversations,
    activeId,
    activeConversation,
    isLoading,
    // nav
    setActiveId,
    createConversation,
    deleteConversation,
    deleteAll,
    renameConversation,
    togglePin,
    // messages
    sendMessage,
    regenerate,
    editAndResend,
    rateMessage,
    // import/export
    exportAll,
    importConversations,
  }
}
