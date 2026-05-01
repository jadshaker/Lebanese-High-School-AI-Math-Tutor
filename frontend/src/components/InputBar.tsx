import { FileText, Image, Paperclip, Send, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { Attachment } from '../api/types'

const MAX_ATTACHMENTS = 5
const MAX_TEXT_BYTES = 200_000 // 200 KB cap for text files

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((res, rej) => {
    const reader = new FileReader()
    reader.onload = () => res(reader.result as string)
    reader.onerror = rej
    reader.readAsDataURL(file)
  })
}

function readAsText(file: File): Promise<string> {
  return new Promise((res, rej) => {
    const reader = new FileReader()
    reader.onload = () => res(reader.result as string)
    reader.onerror = rej
    reader.readAsText(file)
  })
}

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

function fileType(file: File): Attachment['type'] {
  if (file.type.startsWith('image/')) return 'image'
  if (
    file.type.startsWith('text/') ||
    file.name.endsWith('.md') ||
    file.name.endsWith('.csv') ||
    file.name.endsWith('.json') ||
    file.name.endsWith('.txt')
  )
    return 'text'
  return 'other'
}

// ── Attachment chip ───────────────────────────────────────────────────────────

function AttachmentChip({
  attachment,
  onRemove,
}: {
  attachment: Attachment
  onRemove: () => void
}) {
  return (
    <div className="flex items-center gap-1.5 bg-surface border border-border rounded-lg pl-2 pr-1 py-1 max-w-[180px]">
      {attachment.type === 'image' && attachment.dataUrl ? (
        <img src={attachment.dataUrl} alt={attachment.name} className="w-6 h-6 rounded object-cover shrink-0" />
      ) : attachment.type === 'text' ? (
        <FileText className="w-3.5 h-3.5 text-indigo shrink-0" />
      ) : (
        <Paperclip className="w-3.5 h-3.5 text-slate-500 shrink-0" />
      )}
      <div className="flex flex-col min-w-0">
        <span className="text-xs text-slate-300 truncate leading-none">{attachment.name}</span>
        <span className="text-[10px] text-slate-600">{formatBytes(attachment.size)}</span>
      </div>
      <button
        onClick={onRemove}
        className="p-0.5 rounded hover:bg-hover text-slate-600 hover:text-slate-300 shrink-0"
      >
        <X className="w-3 h-3" />
      </button>
    </div>
  )
}

// ── Main InputBar ─────────────────────────────────────────────────────────────

interface Props {
  onSend: (text: string, attachments?: Attachment[]) => void
  disabled: boolean
  pendingAttachment?: Attachment | null
  onClearPendingAttachment?: () => void
}

export function InputBar({ onSend, disabled, pendingAttachment, onClearPendingAttachment }: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [uploading, setUploading] = useState(false)

  // Inject a pending attachment from Math Canvas export
  useEffect(() => {
    if (!pendingAttachment) return
    setAttachments((prev) => {
      if (prev.find((a) => a.id === pendingAttachment.id)) return prev
      return [...prev, pendingAttachment]
    })
    onClearPendingAttachment?.()
    textareaRef.current?.focus()
  }, [pendingAttachment, onClearPendingAttachment])

  const removeAttachment = useCallback((id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id))
  }, [])

  const handleFiles = useCallback(async (files: FileList | null) => {
    if (!files) return
    const remaining = MAX_ATTACHMENTS - attachments.length
    const toProcess = Array.from(files).slice(0, remaining)
    if (!toProcess.length) return

    setUploading(true)
    const results: Attachment[] = []
    for (const file of toProcess) {
      const type = fileType(file)
      const base: Omit<Attachment, 'dataUrl' | 'textContent'> = {
        id: crypto.randomUUID(),
        name: file.name,
        type,
        mimeType: file.type,
        size: file.size,
      }
      try {
        if (type === 'image') {
          const dataUrl = await readAsDataUrl(file)
          results.push({ ...base, dataUrl })
        } else if (type === 'text' && file.size <= MAX_TEXT_BYTES) {
          const textContent = await readAsText(file)
          results.push({ ...base, textContent })
        } else {
          results.push(base)
        }
      } catch {
        results.push(base)
      }
    }
    setAttachments((prev) => [...prev, ...results])
    setUploading(false)
  }, [attachments.length])

  const submit = useCallback(() => {
    const text = textareaRef.current?.value.trim() ?? ''
    if ((!text && attachments.length === 0) || disabled) return
    onSend(text, attachments.length > 0 ? attachments : undefined)
    if (textareaRef.current) {
      textareaRef.current.value = ''
      textareaRef.current.style.height = 'auto'
    }
    setAttachments([])
  }, [onSend, disabled, attachments])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const el = e.target
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }

  // Drag-and-drop support
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    handleFiles(e.dataTransfer.files)
  }

  return (
    <div
      className="px-4 py-3 border-t border-border bg-panel"
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
    >
      {/* Attachment chips */}
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {attachments.map((a) => (
            <AttachmentChip key={a.id} attachment={a} onRemove={() => removeAttachment(a.id)} />
          ))}
        </div>
      )}

      {/* Input row */}
      <div className="flex items-end gap-2 bg-surface border border-border rounded-xl px-3 py-2 focus-within:border-indigo/50 transition-colors">
        {/* Attach button */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled || uploading || attachments.length >= MAX_ATTACHMENTS}
          title="Attach file or image"
          className={`shrink-0 p-1 rounded transition-colors mb-0.5 ${
            attachments.length >= MAX_ATTACHMENTS || disabled
              ? 'text-slate-700 cursor-not-allowed'
              : 'text-slate-500 hover:text-slate-300 hover:bg-hover'
          }`}
        >
          {uploading ? (
            <span className="w-4 h-4 rounded-full border-2 border-slate-600 border-t-slate-400 animate-spin block" />
          ) : (
            <Paperclip className="w-4 h-4" strokeWidth={1.5} />
          )}
        </button>

        <textarea
          ref={textareaRef}
          rows={1}
          placeholder={
            attachments.length > 0
              ? 'Add a message or send the attachment…'
              : 'Ask a math question… (Enter to send, Shift+Enter for newline)'
          }
          disabled={disabled}
          onKeyDown={handleKeyDown}
          onChange={handleInput}
          className="flex-1 resize-none bg-transparent text-sm text-slate-200 placeholder-slate-600 outline-none leading-relaxed max-h-40 overflow-y-auto"
        />

        <button
          onClick={submit}
          disabled={disabled}
          title="Send (Enter)"
          className={`shrink-0 w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${
            disabled
              ? 'bg-surface text-slate-600 cursor-not-allowed'
              : 'bg-indigo/20 text-indigo border border-indigo/40 hover:bg-indigo/30'
          }`}
        >
          {disabled ? (
            <span className="w-3 h-3 rounded-full border-2 border-indigo/40 border-t-indigo animate-spin" />
          ) : (
            <Send className="w-4 h-4" strokeWidth={1.5} />
          )}
        </button>
      </div>

      <div className="flex items-center justify-between mt-1.5">
        <p className="text-xs text-slate-700">
          Supports LaTeX math — e.g.{' '}
          <span className="text-slate-600">$x^2 + y^2 = r^2$</span>
        </p>
        <div className="flex items-center gap-1.5 text-xs text-slate-700">
          <Image className="w-3 h-3" />
          <span>images</span>
          <FileText className="w-3 h-3 ml-1" />
          <span>text files</span>
        </div>
      </div>

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept="image/*,.txt,.md,.csv,.json,.py,.js,.ts"
        className="hidden"
        onChange={(e) => { handleFiles(e.target.files); e.target.value = '' }}
      />
    </div>
  )
}
