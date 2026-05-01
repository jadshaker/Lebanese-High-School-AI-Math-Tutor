import { motion } from 'framer-motion'
import { BookOpen, Sigma } from 'lucide-react'

const EXAMPLES = [
  'What is the derivative of x² + 3x?',
  'Solve the equation 2x² - 5x + 3 = 0',
  'Prove that √2 is irrational',
  'Explain the chain rule with an example',
  'Find the integral of sin(x)cos(x)',
]

interface Props {
  onSelect: (q: string) => void
}

export function WelcomeScreen({ onSelect }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="flex flex-col items-center justify-center h-full gap-8 px-6 text-center select-none"
    >
      {/* Icon + heading */}
      <div className="flex flex-col items-center gap-4">
        <div className="relative">
          <div className="w-16 h-16 rounded-2xl bg-gold/10 border border-gold/30 flex items-center justify-center">
            <BookOpen className="w-8 h-8 text-gold" strokeWidth={1.5} />
          </div>
          <div className="absolute -bottom-1 -right-1 w-6 h-6 rounded-lg bg-indigo/20 border border-indigo/40 flex items-center justify-center">
            <Sigma className="w-3.5 h-3.5 text-indigo" strokeWidth={1.5} />
          </div>
        </div>
        <div>
          <h1 className="text-2xl font-semibold text-slate-100 mb-1">
            Math <span className="text-gold">Atelier</span>
          </h1>
          <p className="text-sm text-slate-500 max-w-xs leading-relaxed">
            Your personal AI mathematics tutor for the Lebanese high school curriculum. Ask any
            question — I will guide you step by step.
          </p>
        </div>
      </div>

      {/* Example questions */}
      <div className="flex flex-col gap-2 w-full max-w-sm">
        <p className="text-xs text-slate-600 uppercase tracking-widest mb-1">Try asking</p>
        {EXAMPLES.map((q) => (
          <motion.button
            key={q}
            whileHover={{ x: 4 }}
            onClick={() => onSelect(q)}
            className="text-left text-sm text-slate-400 px-4 py-2.5 rounded-lg border border-border bg-surface hover:border-gold/40 hover:text-slate-200 hover:bg-gold/5 transition-colors"
          >
            {q}
          </motion.button>
        ))}
      </div>
    </motion.div>
  )
}
