import { AnimatePresence, motion } from 'framer-motion'
import { Download, LogIn, Trash2, Upload, X } from 'lucide-react'
import { useRef, useState } from 'react'
import type { UserProfile } from '../hooks/useUserProfile'

interface Props {
  isOpen: boolean
  onClose: () => void
  profile: UserProfile
  onSaveProfile: (update: Partial<UserProfile>) => void
  onDeleteAll: () => void
  onExport: () => void
  onImport: (file: File) => void
}

export function SettingsModal({
  isOpen,
  onClose,
  profile,
  onSaveProfile,
  onDeleteAll,
  onExport,
  onImport,
}: Props) {
  const [tab, setTab] = useState<'profile' | 'data'>('profile')
  const [name, setName] = useState(profile.displayName)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleSave = () => {
    onSaveProfile({ displayName: name.trim() || 'Student' })
    onClose()
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 z-50 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Panel */}
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 16 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none"
          >
            <div
              className="pointer-events-auto w-full max-w-md bg-panel border border-border rounded-2xl shadow-2xl flex flex-col overflow-hidden"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header */}
              <div className="flex items-center justify-between px-5 py-4 border-b border-border">
                <h2 className="text-sm font-semibold text-slate-200">Settings</h2>
                <button
                  onClick={onClose}
                  className="p-1.5 rounded-lg hover:bg-hover text-slate-500 hover:text-slate-300 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Tabs */}
              <div className="flex gap-1 px-5 pt-3">
                {(['profile', 'data'] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTab(t)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-colors ${
                      tab === t
                        ? 'bg-indigo/20 text-indigo border border-indigo/30'
                        : 'text-slate-500 hover:text-slate-300'
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>

              {/* Body */}
              <div className="px-5 py-4 flex-1 overflow-y-auto space-y-4">
                {tab === 'profile' && (
                  <div className="space-y-4">
                    <div>
                      <label className="block text-xs text-slate-400 mb-1.5">Display Name</label>
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-full bg-gold/20 border border-gold/30 flex items-center justify-center text-xs font-semibold text-gold shrink-0">
                          {name ? name[0].toUpperCase() : '?'}
                        </div>
                        <input
                          value={name}
                          onChange={(e) => setName(e.target.value)}
                          placeholder="Enter your name"
                          className="flex-1 bg-surface border border-border rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 outline-none focus:border-indigo/50 transition-colors"
                        />
                      </div>
                    </div>

                    <div className="p-3 rounded-lg bg-surface border border-border">
                      <p className="text-xs text-slate-400 font-medium mb-1">Model</p>
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-emerald animate-pulse-slow" />
                        <span className="text-xs text-slate-300">math-tutor</span>
                        <span className="text-xs text-slate-600 ml-auto">Lebanese HS Curriculum</span>
                      </div>
                    </div>
                  </div>
                )}

                {tab === 'data' && (
                  <div className="space-y-3">
                    <div className="p-3 rounded-lg bg-surface border border-border space-y-2">
                      <p className="text-xs text-slate-400 font-medium">Conversations</p>
                      <button
                        onClick={onExport}
                        className="flex items-center gap-2 w-full px-3 py-2 rounded-lg border border-border hover:border-indigo/40 text-xs text-slate-300 hover:text-slate-200 transition-colors"
                      >
                        <Download className="w-3.5 h-3.5 text-indigo" />
                        Export all as JSON
                      </button>
                      <button
                        onClick={() => fileInputRef.current?.click()}
                        className="flex items-center gap-2 w-full px-3 py-2 rounded-lg border border-border hover:border-indigo/40 text-xs text-slate-300 hover:text-slate-200 transition-colors"
                      >
                        <Upload className="w-3.5 h-3.5 text-indigo" />
                        Import from JSON
                      </button>
                    </div>

                    <div className="p-3 rounded-lg bg-rose/5 border border-rose/20 space-y-2">
                      <p className="text-xs text-rose font-medium">Danger Zone</p>
                      {!confirmDelete ? (
                        <button
                          onClick={() => setConfirmDelete(true)}
                          className="flex items-center gap-2 w-full px-3 py-2 rounded-lg border border-rose/30 text-xs text-rose hover:bg-rose/10 transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          Delete all conversations
                        </button>
                      ) : (
                        <div className="space-y-2">
                          <p className="text-xs text-slate-400">This cannot be undone. Are you sure?</p>
                          <div className="flex gap-2">
                            <button
                              onClick={() => { onDeleteAll(); setConfirmDelete(false); onClose() }}
                              className="flex-1 py-1.5 rounded-lg bg-rose/20 border border-rose/40 text-xs text-rose hover:bg-rose/30 transition-colors"
                            >
                              Yes, delete all
                            </button>
                            <button
                              onClick={() => setConfirmDelete(false)}
                              className="flex-1 py-1.5 rounded-lg bg-surface border border-border text-xs text-slate-300 hover:bg-hover transition-colors"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="flex justify-end gap-2 px-5 pb-4 pt-2 border-t border-border">
                <button
                  onClick={onClose}
                  className="px-4 py-2 rounded-lg text-xs text-slate-400 hover:text-slate-200 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSave}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo/20 border border-indigo/40 text-xs text-indigo hover:bg-indigo/30 transition-colors"
                >
                  <LogIn className="w-3.5 h-3.5" />
                  Save
                </button>
              </div>
            </div>
          </motion.div>

          <input
            ref={fileInputRef}
            type="file"
            accept=".json"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) { onImport(f); onClose() }
              e.target.value = ''
            }}
          />
        </>
      )}
    </AnimatePresence>
  )
}
