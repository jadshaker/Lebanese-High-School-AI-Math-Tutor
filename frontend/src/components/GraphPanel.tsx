import cytoscape from 'cytoscape'
import { motion } from 'framer-motion'
import { Activity, MapPin, Radio, Wifi, WifiOff } from 'lucide-react'
import { useEffect, useRef } from 'react'
import type { GraphEvent, GraphTree } from '../api/types'

// ── Cytoscape stylesheet ──────────────────────────────────────────────────────
const cytoscapeStyle: cytoscape.StylesheetStyle[] = [
  {
    selector: 'node',
    style: {
      'background-color': '#1a1a28',
      'border-width': 2,
      'border-color': '#3a3a5c',
      color: '#94a3b8',
      'font-size': 10,
      'font-family': 'Inter, system-ui, sans-serif',
      'text-valign': 'bottom',
      'text-margin-y': 6,
      label: 'data(shortLabel)',
      width: 28,
      height: 28,
      'text-max-width': '120px',
      'text-wrap': 'ellipsis',
      'text-overflow-wrap': 'whitespace',
    },
  },
  {
    selector: 'node[type = "root"]',
    style: {
      'background-color': '#1a1000',
      'border-color': '#f59e0b',
      'border-width': 2.5,
      color: '#f59e0b',
      width: 34,
      height: 34,
      shape: 'diamond',
    },
  },
  {
    selector: 'node[type = "interaction"]',
    style: {
      'background-color': '#0d0d2e',
      'border-color': '#818cf8',
      color: '#818cf8',
      shape: 'round-rectangle',
    },
  },
  {
    selector: 'node.current',
    style: {
      'border-color': '#34d399',
      'border-width': 3,
      color: '#34d399',
      'background-color': '#052015',
    },
  },
  {
    selector: 'edge',
    style: {
      width: 1.5,
      'line-color': '#2a2a42',
      'target-arrow-color': '#3a3a5c',
      'target-arrow-shape': 'triangle',
      'curve-style': 'bezier',
      'arrow-scale': 0.8,
    },
  },
]

// ── Event pill ────────────────────────────────────────────────────────────────
const EVENT_META: Record<
  string,
  { label: string; color: string }
> = {
  cache_hit: { label: 'cache hit', color: 'text-emerald border-emerald/30 bg-emerald/10' },
  cache_miss: { label: 'cache miss', color: 'text-rose border-rose/30 bg-rose/10' },
  cache_search: { label: 'searching', color: 'text-gold border-gold/30 bg-gold/10' },
  node_created: { label: 'new node', color: 'text-indigo border-indigo/30 bg-indigo/10' },
  position_update: { label: 'moved', color: 'text-slate-400 border-slate-600 bg-surface' },
  session_created: { label: 'session', color: 'text-emerald border-emerald/30 bg-emerald/10' },
  session_start: { label: 'started', color: 'text-slate-400 border-slate-600 bg-surface' },
  correction: { label: 'correction', color: 'text-rose border-rose/30 bg-rose/10' },
}

function EventPill({ event }: { event: GraphEvent & { id: string } }) {
  const meta = EVENT_META[event.type] ?? {
    label: event.type,
    color: 'text-slate-400 border-slate-600 bg-surface',
  }
  return (
    <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded border text-xs ${meta.color}`}>
      <Radio className="w-2.5 h-2.5" />
      {meta.label}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
interface Props {
  graphTree: GraphTree | null
  events: (GraphEvent & { id: string })[]
  depth: number
  isConnected: boolean
  sessionId: string | null
}

export function GraphPanel({ graphTree, events, depth, isConnected, sessionId }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)

  // Initialize or update Cytoscape when graphTree changes
  useEffect(() => {
    if (!containerRef.current) return

    if (!graphTree || (graphTree.nodes.length === 0 && graphTree.edges.length === 0)) {
      cyRef.current?.destroy()
      cyRef.current = null
      return
    }

    // Add shortLabel to each node
    const nodes = graphTree.nodes.map((n) => ({
      data: {
        ...n.data,
        shortLabel:
          n.data.type === 'root'
            ? (n.data.label ?? 'Q').slice(0, 22) + (n.data.label?.length > 22 ? '…' : '')
            : (n.data.user_input ?? '…').slice(0, 18) + ((n.data.user_input?.length ?? 0) > 18 ? '…' : ''),
      },
    }))

    cyRef.current?.destroy()

    const cy = cytoscape({
      container: containerRef.current,
      elements: { nodes, edges: graphTree.edges },
      style: cytoscapeStyle,
      layout: {
        name: 'breadthfirst',
        directed: true,
        padding: 20,
        spacingFactor: 1.4,
      } as cytoscape.BreadthFirstLayoutOptions,
      userZoomingEnabled: true,
      userPanningEnabled: true,
      minZoom: 0.3,
      maxZoom: 3,
    })

    // Tooltip on hover
    cy.on('mouseover', 'node', (evt) => {
      const node = evt.target as cytoscape.NodeSingular
      const d = node.data() as { user_input?: string; system_response?: string; label?: string }
      const tip = d.user_input
        ? `Q: ${d.user_input?.slice(0, 80)}`
        : d.label?.slice(0, 80) ?? ''
      node.data('tooltip', tip)
    })

    cyRef.current = cy

    return () => {
      cy.destroy()
      cyRef.current = null
    }
  }, [graphTree])

  const isEmpty = !graphTree || graphTree.nodes.length === 0

  return (
    <div className="flex flex-col h-full bg-panel border-l border-border min-h-0">
      {/* Panel header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border shrink-0">
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <Activity className="w-3.5 h-3.5 text-indigo" />
          <span className="font-medium text-slate-300">Knowledge Map</span>
        </div>
        <div className="flex items-center gap-2">
          {sessionId && (
            <div className="flex items-center gap-1 text-xs text-slate-500">
              <MapPin className="w-3 h-3" />
              depth <span className="text-indigo font-semibold">{depth}</span>
            </div>
          )}
          <div className={`flex items-center gap-1 text-xs ${isConnected ? 'text-emerald' : 'text-slate-600'}`}>
            {isConnected ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
            <span className="hidden sm:inline">{isConnected ? 'live' : 'idle'}</span>
          </div>
        </div>
      </div>

      {/* Cytoscape canvas */}
      <div className="flex-1 relative min-h-0">
        <div ref={containerRef} className="absolute inset-0" />

        {isEmpty && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-center px-6 pointer-events-none"
          >
            <div className="w-12 h-12 rounded-xl bg-surface border border-border flex items-center justify-center">
              <Activity className="w-6 h-6 text-slate-600" strokeWidth={1.5} />
            </div>
            <p className="text-xs text-slate-600 max-w-[160px] leading-relaxed">
              {sessionId
                ? 'Building knowledge map…'
                : 'Start a conversation to see your learning graph'}
            </p>
          </motion.div>
        )}
      </div>

      {/* Event feed */}
      {events.length > 0 && (
        <div className="border-t border-border px-3 py-2 shrink-0">
          <p className="text-xs text-slate-600 mb-1.5 uppercase tracking-widest">Recent activity</p>
          <div className="flex flex-wrap gap-1.5 max-h-20 overflow-y-auto">
            {events.slice(0, 10).map((e) => (
              <EventPill key={e.id} event={e} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
