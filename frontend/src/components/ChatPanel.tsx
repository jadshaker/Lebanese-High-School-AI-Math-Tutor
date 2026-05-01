import { AnimatePresence } from 'framer-motion'
import { useEffect, useRef } from 'react'
import type { Attachment, Message } from '../api/types'
import { InputBar } from './InputBar'
import { MessageBlock } from './MessageBlock'
import { WelcomeScreen } from './WelcomeScreen'

interface Props {
  messages: Message[]
  isLoading: boolean
  onSend: (text: string, attachments?: Attachment[]) => void
  onRegenerate: () => void
  onEditResend: (id: string, newText: string) => void
  onRate: (id: string, rating: 'up' | 'down') => void
  pendingAttachment?: Attachment | null
  onClearPendingAttachment?: () => void
}

export function ChatPanel({ messages, isLoading, onSend, onRegenerate, onEditResend, onRate, pendingAttachment, onClearPendingAttachment }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Find the last non-loading assistant message index
  const lastAiIdx = messages.reduceRight(
    (acc, m, i) => (acc === -1 && m.role === 'assistant' && !m.isLoading ? i : acc),
    -1,
  )

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-5 scrollbar-thin">
        {messages.length === 0 ? (
          <WelcomeScreen onSelect={onSend} />
        ) : (
          <AnimatePresence initial={false}>
            {messages.map((msg, idx) => (
              <MessageBlock
                key={msg.id}
                message={msg}
                isLastAssistant={idx === lastAiIdx}
                onRegenerate={onRegenerate}
                onEditResend={onEditResend}
                onRate={onRate}
              />
            ))}
          </AnimatePresence>
        )}
        <div ref={bottomRef} />
      </div>

      <InputBar
        onSend={onSend}
        disabled={isLoading}
        pendingAttachment={pendingAttachment}
        onClearPendingAttachment={onClearPendingAttachment}
      />
    </div>
  )
}
