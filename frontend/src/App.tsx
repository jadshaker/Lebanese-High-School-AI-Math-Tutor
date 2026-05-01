import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import type { Attachment } from './api/types'
import { useConversationStore } from './hooks/useConversationStore'
import { useGraph } from './hooks/useGraph'
import { useHealth } from './hooks/useHealth'
import { useUserProfile } from './hooks/useUserProfile'
import { ChatPanel } from './components/ChatPanel'
import { GraphPanel } from './components/GraphPanel'
import { Header } from './components/Header'
import { SettingsModal } from './components/SettingsModal'
import { SetupModal } from './components/SetupModal'
import { Sidebar } from './components/Sidebar'

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [graphOpen, setGraphOpen] = useState(true)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [pendingAttachment, setPendingAttachment] = useState<Attachment | null>(null)

  const { profile, setProfile, initials } = useUserProfile()

  const {
    conversations,
    activeId,
    activeConversation,
    isLoading,
    setActiveId,
    createConversation,
    deleteConversation,
    deleteAll,
    renameConversation,
    togglePin,
    sendMessage,
    regenerate,
    editAndResend,
    rateMessage,
    exportAll,
    importConversations,
  } = useConversationStore()

  const sessionId = activeConversation?.sessionId ?? null
  const { graphTree, events, depth, isConnected } = useGraph(sessionId)
  const { health, offline } = useHealth()

  // Keyboard shortcut: Ctrl+K focuses sidebar search (future) or opens search
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        setSidebarOpen(true)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  // Receive exports sent from Math Canvas (mathcanvas.html via postMessage)
  useEffect(() => {
    const handler = (e: MessageEvent) => {
      if (e.data?.type !== 'mathcanvas-export') return
      const { dataUrl, mimeType, filename } = e.data as {
        type: string
        dataUrl: string
        mimeType: string
        filename: string
      }
      const attachment: Attachment = {
        id: crypto.randomUUID(),
        name: filename,
        type: 'image',
        mimeType,
        dataUrl,
        size: Math.round((dataUrl.length * 3) / 4),
      }
      setPendingAttachment(attachment)
    }
    window.addEventListener('message', handler)
    return () => window.removeEventListener('message', handler)
  }, [])

  const messages = activeConversation?.messages ?? []

  return (
    <>
      {/* First-time setup */}
      {!profile.setupDone && (
        <SetupModal
          onComplete={(name) => setProfile({ displayName: name, setupDone: true })}
        />
      )}

      <div className="flex flex-col h-full bg-base text-slate-200 overflow-hidden">
        <Header
          health={health}
          offline={offline}
          sessionId={sessionId}
          depth={depth}
          graphOpen={graphOpen}
          onToggleGraph={() => setGraphOpen((v) => !v)}
          onOpenSettings={() => setSettingsOpen(true)}
          displayName={profile.displayName}
          initials={initials}
        />

        <div className="flex flex-1 min-h-0">
          {/* Sidebar */}
          <Sidebar
            conversations={conversations}
            activeId={activeId}
            onSelect={setActiveId}
            onNew={createConversation}
            onDelete={deleteConversation}
            onRename={renameConversation}
            onTogglePin={togglePin}
            onExport={exportAll}
            onImport={importConversations}
            isOpen={sidebarOpen}
            onToggle={() => setSidebarOpen((v) => !v)}
          />

          {/* Chat panel with dot-grid background */}
          <div className="flex-1 min-w-0 dot-grid relative">
            <div className="absolute inset-0 pointer-events-none bg-gradient-to-b from-base/60 via-transparent to-base/60 z-0" />
            <div className="relative z-10 h-full">
              <ChatPanel
                messages={messages}
                isLoading={isLoading}
                onSend={sendMessage}
                onRegenerate={regenerate}
                onEditResend={editAndResend}
                onRate={rateMessage}
                pendingAttachment={pendingAttachment}
                onClearPendingAttachment={() => setPendingAttachment(null)}
              />
            </div>
          </div>

          {/* Graph panel */}
          <AnimatePresence>
            {graphOpen && (
              <motion.div
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: 340, opacity: 1 }}
                exit={{ width: 0, opacity: 0 }}
                transition={{ duration: 0.22, ease: 'easeInOut' }}
                className="shrink-0 overflow-hidden"
                style={{ minHeight: 0 }}
              >
                <div className="w-[340px] h-full">
                  <GraphPanel
                    graphTree={graphTree}
                    events={events}
                    depth={depth}
                    isConnected={isConnected}
                    sessionId={sessionId}
                  />
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Settings modal */}
      <SettingsModal
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        profile={profile}
        onSaveProfile={setProfile}
        onDeleteAll={deleteAll}
        onExport={exportAll}
        onImport={importConversations}
      />
    </>
  )
}
