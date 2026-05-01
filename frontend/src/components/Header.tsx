import { BookOpen, Compass, GitBranch, Network, Settings, Wifi, WifiOff } from 'lucide-react'
import type { HealthResponse } from '../api/types'

interface Props {
  health: HealthResponse | null
  offline: boolean
  sessionId: string | null
  depth: number
  graphOpen: boolean
  onToggleGraph: () => void
  onOpenSettings: () => void
  displayName: string
  initials: string
}

export function Header({
  health,
  offline,
  sessionId,
  depth,
  graphOpen,
  onToggleGraph,
  onOpenSettings,
  displayName,
  initials,
}: Props) {
  const statusColor = offline
    ? 'bg-rose'
    : health?.status === 'healthy'
      ? 'bg-emerald'
      : 'bg-gold'

  const statusLabel = offline ? 'offline' : (health?.status ?? 'connecting…')

  return (
    <header className="h-12 flex items-center justify-between px-4 border-b border-border bg-panel shrink-0 z-20">
      {/* Brand */}
      <div className="flex items-center gap-2">
        <BookOpen className="w-5 h-5 text-gold" strokeWidth={1.5} />
        <span className="text-sm font-semibold text-slate-100">
          Math <span className="text-gold">Atelier</span>
        </span>
      </div>

      {/* Centre: status */}
      <div className="hidden md:flex items-center gap-3">
        <div className="flex items-center gap-1.5 text-xs">
          <span className={`w-1.5 h-1.5 rounded-full ${statusColor}`} />
          <span className="text-slate-500 capitalize">{statusLabel}</span>
          {offline ? (
            <WifiOff className="w-3 h-3 text-rose" />
          ) : (
            <Wifi className="w-3 h-3 text-slate-600" />
          )}
        </div>
        {health && (
          <span className="text-xs text-slate-600">
            {health.active_sessions} active session{health.active_sessions !== 1 ? 's' : ''}
          </span>
        )}
        {sessionId && (
          <div className="flex items-center gap-1 px-2 py-0.5 rounded bg-indigo-faint border border-indigo/25 text-xs text-indigo">
            <GitBranch className="w-3 h-3" />
            depth {depth}
          </div>
        )}
      </div>

      {/* Right: graph toggle + settings + avatar */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => window.open('/mathcanvas.html', '_blank')}
          title="Open Math Canvas — Interactive Geometry"
          className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs transition-colors bg-surface text-slate-400 border border-border hover:border-gold/40 hover:text-gold"
        >
          <Compass className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Canvas</span>
        </button>

        <button
          onClick={onToggleGraph}
          title={graphOpen ? 'Hide knowledge map' : 'Show knowledge map'}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs transition-colors ${
            graphOpen
              ? 'bg-indigo/20 text-indigo border border-indigo/40'
              : 'bg-surface text-slate-400 border border-border hover:border-indigo/40 hover:text-indigo'
          }`}
        >
          <Network className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Map</span>
        </button>

        <button
          onClick={onOpenSettings}
          title="Settings"
          className="p-1.5 rounded hover:bg-hover text-slate-500 hover:text-slate-300 transition-colors"
        >
          <Settings className="w-4 h-4" />
        </button>

        {/* Avatar */}
        <button
          onClick={onOpenSettings}
          title={displayName || 'Profile'}
          className="w-7 h-7 rounded-full bg-gold/20 border border-gold/30 flex items-center justify-center text-xs font-semibold text-gold hover:bg-gold/30 transition-colors shrink-0"
        >
          {initials}
        </button>
      </div>
    </header>
  )
}
