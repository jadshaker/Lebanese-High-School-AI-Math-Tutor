import { motion } from 'framer-motion'
import { BookOpen } from 'lucide-react'
import { useState } from 'react'

interface Props {
  onComplete: (name: string) => void
}

export function SetupModal({ onComplete }: Props) {
  const [name, setName] = useState('')

  return (
    <div className="fixed inset-0 z-50 bg-base flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: 'easeOut' }}
        className="w-full max-w-sm"
      >
        {/* Icon */}
        <div className="flex justify-center mb-6">
          <div className="w-16 h-16 rounded-2xl bg-gold/10 border border-gold/30 flex items-center justify-center">
            <BookOpen className="w-8 h-8 text-gold" strokeWidth={1.5} />
          </div>
        </div>

        {/* Heading */}
        <h1 className="text-center text-2xl font-semibold text-slate-100 mb-1">
          Welcome to Math <span className="text-gold">Atelier</span>
        </h1>
        <p className="text-center text-sm text-slate-500 mb-8 leading-relaxed">
          Your AI mathematics tutor for the Lebanese high school curriculum.
          <br />What should I call you?
        </p>

        {/* Form */}
        <div className="space-y-3">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && name.trim()) onComplete(name.trim()) }}
            placeholder="Your name or nickname"
            autoFocus
            className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-sm text-slate-200 placeholder-slate-600 outline-none focus:border-indigo/50 transition-colors text-center"
          />
          <button
            onClick={() => onComplete(name.trim() || 'Student')}
            className="w-full py-3 rounded-xl bg-gold/15 border border-gold/30 text-sm font-medium text-gold hover:bg-gold/25 transition-colors"
          >
            Get Started
          </button>
          <button
            onClick={() => onComplete('Student')}
            className="w-full py-2 text-xs text-slate-600 hover:text-slate-400 transition-colors"
          >
            Continue as guest
          </button>
        </div>
      </motion.div>
    </div>
  )
}
