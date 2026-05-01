import { AnimatePresence, motion } from 'framer-motion'
import {
  Download,
  MessageSquarePlus,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  Pin,
  PinOff,
  Search,
  Trash2,
  Upload,
} from 'lucide-react'
import { useRef, useState } from 'react'
import type { Conversation } from '../hooks/useConversationStore'

// ── Time group helper ─────────────────────────────────────────────────────────

function timeGroup(dateStr: string): string {
  const d = new Date(dateStr)
  const now = new Date()
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86_400_000)
  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (diffDays <= 7) return 'Last 7 days'
  if (diffDays <= 30) return 'Last 30 days'
  return d.toLocaleString('default', { month: 'long', year: 'numeric' })
}

// ── Context menu for a single conversation ────────────────────────────────────

interface ItemMenuProps {
  conv: Conversation
  onRename: () => void
  onDelete: () => void
  onTogglePin: () => void
}

function ItemMenu({ conv, onRename, onDelete, onTogglePin }: ItemMenuProps) {
  const [open, setOpen] = useState(false)

  return (
    <div className="relative">
      <button
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v) }}
        className="p-1 rounded hover:bg-hover text-slate-500 hover:text-slate-300 transition-colors"
      >
        <MoreHorizontal className="w-3.5 h-3.5" />
      </button>
      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: -4 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: -4 }}
              transition={{ duration: 0.1 }}
              className="absolute right-0 top-6 z-50 bg-surface border border-border rounded-lg shadow-xl py-1 w-36"
            >
              <button
                onClick={(e) => { e.stopPropagation(); onTogglePin(); setOpen(false) }}
                className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-slate-300 hover:bg-hover transition-colors"
              >
                {conv.isPinned ? <PinOff className="w-3 h-3" /> : <Pin className="w-3 h-3" />}
                {conv.isPinned ? 'Unpin' : 'Pin'}
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); onRename(); setOpen(false) }}
                className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-slate-300 hover:bg-hover transition-colors"
              >
                <MessageSquarePlus className="w-3 h-3" />
                Rename
              </button>
              <div className="my-1 border-t border-border" />
              <button
                onClick={(e) => { e.stopPropagation(); onDelete(); setOpen(false) }}
                className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-rose hover:bg-rose/10 transition-colors"
              >
                <Trash2 className="w-3 h-3" />
                Delete
              </button>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Single conversation item ──────────────────────────────────────────────────

interface ItemProps {
  conv: Conversation
  isActive: boolean
  onSelect: () => void
  onRename: (id: string) => void
  onDelete: (id: string) => void
  onTogglePin: (id: string) => void
}

function ConvItem({ conv, isActive, onSelect, onRename, onDelete, onTogglePin }: ItemProps) {
  const [editing, setEditing] = useState(false)
  const [editVal, setEditVal] = useState(conv.title)
  const inputRef = useRef<HTMLInputElement>(null)

  const startEdit = () => {
    setEditVal(conv.title)
    setEditing(true)
    setTimeout(() => inputRef.current?.select(), 50)
  }

  const commitEdit = () => {
    onRename(editVal.trim() || 'Untitled')
    setEditing(false)
  }

  return (
    <div
      onClick={onSelect}
      className={`group relative flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors ${
        isActive ? 'bg-indigo/15 border border-indigo/25' : 'hover:bg-hover border border-transparent'
      }`}
    >
      {conv.isPinned && <Pin className="w-2.5 h-2.5 shrink-0 text-gold/60" />}

      <div className="flex-1 min-w-0">
        {editing ? (
          <input
            ref={inputRef}
            value={editVal}
            onChange={(e) => setEditVal(e.target.value)}
            onBlur={commitEdit}
            onKeyDown={(e) => {
              e.stopPropagation()
              if (e.key === 'Enter') commitEdit()
              if (e.key === 'Escape') setEditing(false)
            }}
            onClick={(e) => e.stopPropagation()}
            className="w-full bg-surface border border-indigo/40 rounded px-1.5 py-0.5 text-xs text-slate-200 outline-none"
            autoFocus
          />
        ) : (
          <p className="text-xs text-slate-300 truncate leading-snug">
            {conv.title}
          </p>
        )}
        <p className="text-[10px] text-slate-600 mt-0.5">
          {new Date(conv.updatedAt).toLocaleDateString([], { month: 'short', day: 'numeric' })}
        </p>
      </div>

      {!editing && (
        <div className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          <ItemMenu
            conv={conv}
            onRename={startEdit}
            onDelete={() => onDelete(conv.id)}
            onTogglePin={() => onTogglePin(conv.id)}
          />
        </div>
      )}
    </div>
  )
}

// ── Main Sidebar component ────────────────────────────────────────────────────

interface Props {
  conversations: Conversation[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
  onRename: (id: string, title: string) => void
  onTogglePin: (id: string) => void
  onExport: () => void
  onImport: (file: File) => void
  isOpen: boolean
  onToggle: () => void
}

export function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onRename,
  onTogglePin,
  onExport,
  onImport,
  isOpen,
  onToggle,
}: Props) {
  const [search, setSearch] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const filtered = conversations.filter((c) =>
    search.trim()
      ? c.title.toLowerCase().includes(search.toLowerCase()) ||
        c.messages.some((m) => m.content.toLowerCase().includes(search.toLowerCase()))
      : true,
  )

  const pinned = filtered.filter((c) => c.isPinned).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
  const unpinned = filtered.filter((c) => !c.isPinned).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))

  // Group unpinned by time
  const groups: Record<string, Conversation[]> = {}
  for (const c of unpinned) {
    const g = timeGroup(c.updatedAt)
    if (!groups[g]) groups[g] = []
    groups[g].push(c)
  }

  return (
    <AnimatePresence initial={false}>
      {isOpen ? (
        <motion.aside
          key="open"
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: 260, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ duration: 0.22, ease: 'easeInOut' }}
          className="flex flex-col bg-panel border-r border-border overflow-hidden shrink-0 h-full"
          style={{ minWidth: 0 }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-3 pt-3 pb-2 shrink-0">
            <button
              onClick={onNew}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-gold/10 border border-gold/25 text-gold text-xs font-medium hover:bg-gold/20 transition-colors"
            >
              <MessageSquarePlus className="w-3.5 h-3.5" />
              New Chat
            </button>
            <div className="flex items-center gap-1">
              <button
                title="Export chats"
                onClick={onExport}
                className="p-1.5 rounded hover:bg-hover text-slate-500 hover:text-slate-300 transition-colors"
              >
                <Download className="w-3.5 h-3.5" />
              </button>
              <button
                title="Import chats"
                onClick={() => fileInputRef.current?.click()}
                className="p-1.5 rounded hover:bg-hover text-slate-500 hover:text-slate-300 transition-colors"
              >
                <Upload className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={onToggle}
                title="Collapse sidebar"
                className="p-1.5 rounded hover:bg-hover text-slate-500 hover:text-slate-300 transition-colors"
              >
                <PanelLeftClose className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Search */}
          <div className="px-3 pb-2 shrink-0">
            <div className="flex items-center gap-2 bg-surface border border-border rounded-lg px-2.5 py-1.5">
              <Search className="w-3 h-3 text-slate-600" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search conversations…"
                className="flex-1 bg-transparent text-xs text-slate-300 placeholder-slate-600 outline-none"
              />
            </div>
          </div>

          {/* Conversation list */}
          <div className="flex-1 overflow-y-auto px-2 pb-3 scrollbar-thin space-y-0.5">
            {conversations.length === 0 && (
              <p className="text-xs text-slate-600 text-center mt-8 px-4 leading-relaxed">
                No conversations yet. Start by asking a math question.
              </p>
            )}

            {pinned.length > 0 && (
              <div>
                <p className="px-2 py-1.5 text-[10px] text-slate-600 uppercase tracking-widest font-medium">
                  Pinned
                </p>
                {pinned.map((c) => (
                  <ConvItem
                    key={c.id}
                    conv={c}
                    isActive={c.id === activeId}
                    onSelect={() => onSelect(c.id)}
                    onRename={(t) => onRename(c.id, t)}
                    onDelete={() => onDelete(c.id)}
                    onTogglePin={() => onTogglePin(c.id)}
                  />
                ))}
              </div>
            )}

            {Object.entries(groups).map(([group, items]) => (
              <div key={group}>
                <p className="px-2 py-1.5 text-[10px] text-slate-600 uppercase tracking-widest font-medium">
                  {group}
                </p>
                {items.map((c) => (
                  <ConvItem
                    key={c.id}
                    conv={c}
                    isActive={c.id === activeId}
                    onSelect={() => onSelect(c.id)}
                    onRename={(t) => onRename(c.id, t)}
                    onDelete={() => onDelete(c.id)}
                    onTogglePin={() => onTogglePin(c.id)}
                  />
                ))}
              </div>
            ))}
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept=".json"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) onImport(f)
              e.target.value = ''
            }}
          />
        </motion.aside>
      ) : (
        <motion.div
          key="collapsed"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="flex flex-col items-center gap-2 py-3 px-1.5 border-r border-border bg-panel shrink-0"
        >
          <button
            onClick={onToggle}
            title="Expand sidebar"
            className="p-1.5 rounded hover:bg-hover text-slate-500 hover:text-slate-300 transition-colors"
          >
            <PanelLeftOpen className="w-4 h-4" />
          </button>
          <button
            onClick={onNew}
            title="New chat"
            className="p-1.5 rounded hover:bg-hover text-gold/60 hover:text-gold transition-colors"
          >
            <MessageSquarePlus className="w-4 h-4" />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
