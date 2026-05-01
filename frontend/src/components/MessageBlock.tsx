import { motion } from 'framer-motion'
import {
  AlertCircle,
  Bot,
  Check,
  Copy,
  FileText,
  Paperclip,
  Pencil,
  RefreshCw,
  ThumbsDown,
  ThumbsUp,
  User,
  X,
} from 'lucide-react'
import { useCallback, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkMath from 'remark-math'
import type { Attachment, Message } from '../api/types'

// ── Attachment display (in message bubble) ────────────────────────────────────

function AttachmentDisplay({ attachments }: { attachments: Attachment[] }) {
  const images = attachments.filter((a) => a.type === 'image' && a.dataUrl)
  const others = attachments.filter((a) => a.type !== 'image' || !a.dataUrl)

  return (
    <div className="space-y-2 mb-2">
      {/* Image grid */}
      {images.length > 0 && (
        <div className={`grid gap-1.5 ${images.length > 1 ? 'grid-cols-2' : 'grid-cols-1'}`}>
          {images.map((a) => (
            <a key={a.id} href={a.dataUrl} target="_blank" rel="noopener noreferrer">
              <img
                src={a.dataUrl}
                alt={a.name}
                className="rounded-lg object-cover max-h-52 w-full cursor-pointer hover:opacity-90 transition-opacity border border-white/10"
              />
            </a>
          ))}
        </div>
      )}
      {/* Non-image file chips */}
      {others.map((a) => (
        <div
          key={a.id}
          className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-black/20 border border-white/10 text-xs"
        >
          {a.type === 'text' ? (
            <FileText className="w-3.5 h-3.5 text-indigo shrink-0" />
          ) : (
            <Paperclip className="w-3.5 h-3.5 text-slate-500 shrink-0" />
          )}
          <span className="text-slate-300 truncate">{a.name}</span>
          <span className="text-slate-600 ml-auto shrink-0">
            {(a.size / 1024).toFixed(1)} KB
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Typing dots ───────────────────────────────────────────────────────────────

function ThinkingDots() {
  return (
    <div className="flex items-center gap-1.5 py-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-2 h-2 rounded-full bg-indigo/70"
          style={{ animation: `thinking 1.4s ease-in-out ${i * 0.16}s infinite` }}
        />
      ))}
    </div>
  )
}

// ── Copy button ───────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }
  return (
    <button
      onClick={copy}
      title="Copy"
      className="p-1 rounded hover:bg-hover text-slate-600 hover:text-slate-300 transition-colors"
    >
      {copied ? <Check className="w-3.5 h-3.5 text-emerald" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  )
}

// ── LaTeX delimiter normaliser ────────────────────────────────────────────────
// DeepSeek (and many LLMs) emit \(...\) / \[...\] delimiters; remark-math only
// understands $...$ / $$...$$, so we convert before rendering.
function normaliseLatex(content: string): string {
  return content
    .replace(/\\\[([\s\S]*?)\\\]/g, (_m, math) => `$$${math}$$`)
    .replace(/\\\(([\s\S]*?)\\\)/g, (_m, math) => `$${math}$`)
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  message: Message
  isLastAssistant?: boolean
  onRegenerate?: () => void
  onEditResend?: (id: string, newText: string) => void
  onRate?: (id: string, rating: 'up' | 'down') => void
}

export function MessageBlock({ message, isLastAssistant, onRegenerate, onEditResend, onRate }: Props) {
  const isUser = message.role === 'user'
  const [editing, setEditing] = useState(false)
  const [editVal, setEditVal] = useState(message.content)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const startEdit = useCallback(() => {
    setEditVal(message.content)
    setEditing(true)
    setTimeout(() => {
      const el = textareaRef.current
      if (el) { el.style.height = `${el.scrollHeight}px`; el.focus(); el.select() }
    }, 40)
  }, [message.content])

  const commitEdit = useCallback(() => {
    if (editVal.trim() && onEditResend) {
      onEditResend(message.id, editVal.trim())
    }
    setEditing(false)
  }, [editVal, message.id, onEditResend])

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22 }}
      className={`group flex gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
    >
      {/* Avatar */}
      <div
        className={`shrink-0 w-7 h-7 rounded-lg flex items-center justify-center mt-0.5 ${
          isUser
            ? 'bg-gold/10 border border-gold/30'
            : message.error
              ? 'bg-rose/10 border border-rose/30'
              : 'bg-indigo/10 border border-indigo/30'
        }`}
      >
        {isUser ? (
          <User className="w-3.5 h-3.5 text-gold" strokeWidth={1.5} />
        ) : message.error ? (
          <AlertCircle className="w-3.5 h-3.5 text-rose" strokeWidth={1.5} />
        ) : (
          <Bot className="w-3.5 h-3.5 text-indigo" strokeWidth={1.5} />
        )}
      </div>

      {/* Bubble + actions */}
      <div className={`flex flex-col gap-1 max-w-[82%] ${isUser ? 'items-end' : 'items-start'}`}>
        <div
          className={`rounded-xl px-4 py-3 text-sm leading-relaxed w-full ${
            isUser
              ? 'bg-gold/8 border border-gold/20 text-slate-200 rounded-tr-sm'
              : message.error
                ? 'bg-rose/8 border border-rose/20 text-slate-300 rounded-tl-sm'
                : 'bg-indigo/8 border border-indigo/20 text-slate-200 rounded-tl-sm'
          }`}
        >
          {/* Attachments (images + file chips) */}
          {!message.isLoading && message.attachments && message.attachments.length > 0 && (
            <AttachmentDisplay attachments={message.attachments} />
          )}

          {message.isLoading ? (
            <ThinkingDots />
          ) : editing ? (
            <div className="space-y-2">
              <textarea
                ref={textareaRef}
                value={editVal}
                onChange={(e) => {
                  setEditVal(e.target.value)
                  e.target.style.height = 'auto'
                  e.target.style.height = `${e.target.scrollHeight}px`
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); commitEdit() }
                  if (e.key === 'Escape') setEditing(false)
                }}
                className="w-full bg-transparent text-sm text-slate-200 outline-none resize-none leading-relaxed"
                rows={1}
              />
              <div className="flex gap-1.5 justify-end">
                <button
                  onClick={() => setEditing(false)}
                  className="flex items-center gap-1 px-2.5 py-1 rounded border border-border text-xs text-slate-400 hover:text-slate-200 transition-colors"
                >
                  <X className="w-3 h-3" /> Cancel
                </button>
                <button
                  onClick={commitEdit}
                  className="flex items-center gap-1 px-2.5 py-1 rounded bg-gold/15 border border-gold/30 text-xs text-gold hover:bg-gold/25 transition-colors"
                >
                  <Check className="w-3 h-3" /> Send
                </button>
              </div>
            </div>
          ) : isUser ? (
            <div className="prose prose-invert prose-sm max-w-none prose-p:my-0.5 prose-p:leading-relaxed">
              <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                {normaliseLatex(message.content)}
              </ReactMarkdown>
            </div>
          ) : (
            <div className="prose prose-invert prose-sm max-w-none
              prose-p:my-1 prose-p:leading-relaxed
              prose-headings:text-slate-200 prose-headings:font-semibold
              prose-strong:text-slate-100
              prose-code:text-gold prose-code:bg-gold/10 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs
              prose-pre:bg-surface prose-pre:border prose-pre:border-border prose-pre:rounded-lg
              prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5
            ">
              <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                {normaliseLatex(message.content)}
              </ReactMarkdown>
            </div>
          )}

          {/* Timestamp */}
          {!message.isLoading && !editing && (
            <p className={`text-xs mt-1.5 ${isUser ? 'text-right text-gold/40' : 'text-indigo/40'}`}>
              {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </p>
          )}
        </div>

        {/* Action bar — visible on hover */}
        {!message.isLoading && !editing && (
          <div className={`flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity ${isUser ? 'flex-row-reverse' : ''}`}>
            <CopyButton text={message.content} />

            {isUser && onEditResend && (
              <button
                onClick={startEdit}
                title="Edit and resend"
                className="p-1 rounded hover:bg-hover text-slate-600 hover:text-slate-300 transition-colors"
              >
                <Pencil className="w-3.5 h-3.5" />
              </button>
            )}

            {!isUser && isLastAssistant && onRegenerate && (
              <button
                onClick={onRegenerate}
                title="Regenerate response"
                className="p-1 rounded hover:bg-hover text-slate-600 hover:text-slate-300 transition-colors"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            )}

            {!isUser && !message.error && onRate && (
              <>
                <button
                  onClick={() => onRate(message.id, 'up')}
                  title="Good response"
                  className={`p-1 rounded hover:bg-hover transition-colors ${
                    message.rating === 'up' ? 'text-emerald' : 'text-slate-600 hover:text-slate-300'
                  }`}
                >
                  <ThumbsUp className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => onRate(message.id, 'down')}
                  title="Bad response"
                  className={`p-1 rounded hover:bg-hover transition-colors ${
                    message.rating === 'down' ? 'text-rose' : 'text-slate-600 hover:text-slate-300'
                  }`}
                >
                  <ThumbsDown className="w-3.5 h-3.5" />
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </motion.div>
  )
}
