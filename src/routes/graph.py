import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from src.config import Config
from src.logging_utils import StructuredLogger
from src.services import event_bus
from src.services.session import service as session_service
from src.services.vector_cache import service as vector_cache

logger = StructuredLogger("graph")

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/tree/{question_id}")
async def get_tree(question_id: str):
    """Return full tree JSON for a question (nodes + edges)."""
    nodes = await vector_cache.get_full_tree(question_id)

    # Also fetch the root question for context
    repo = vector_cache.get_repo()
    question = await repo.get_question(question_id)

    graph_nodes = []
    graph_edges = []

    # Add root question node
    if question:
        graph_nodes.append(
            {
                "data": {
                    "id": question_id,
                    "label": (
                        (question.get("question_text", "")[:60] + "...")
                        if len(question.get("question_text", "")) > 60
                        else question.get("question_text", "")
                    ),
                    "full_text": question.get("question_text", ""),
                    "type": "root",
                    "depth": 0,
                }
            }
        )

    for node in nodes:
        node_id = node["id"]
        user_input = node.get("user_input", "")
        label = (user_input[:40] + "...") if len(user_input) > 40 else user_input
        depth = node.get("depth", 1)
        parent_id = node.get("parent_id")

        graph_nodes.append(
            {
                "data": {
                    "id": node_id,
                    "label": label,
                    "full_text": user_input,
                    "response": node.get("system_response", ""),
                    "type": "interaction",
                    "depth": depth,
                }
            }
        )

        # Edge to parent (or root question if depth 1)
        edge_source = parent_id if parent_id else question_id
        graph_edges.append({"data": {"source": edge_source, "target": node_id}})

    return {"nodes": graph_nodes, "edges": graph_edges}


@router.get("/sessions")
async def list_active_sessions():
    """List all active sessions with tutoring state for the session picker."""
    from src.services.session.service import _lock, sessions

    async with _lock:
        result = []
        for sid, data in sessions.items():
            if data.tutoring.question_id:
                result.append(
                    {
                        "session_id": sid,
                        "question_id": data.tutoring.question_id,
                        "original_query": data.original_query or "",
                        "depth": data.tutoring.depth,
                        "current_node_id": data.tutoring.current_node_id,
                        "created_at": (
                            data.created_at.isoformat() if data.created_at else None
                        ),
                    }
                )
    # Most recent first
    result.sort(key=lambda x: x["created_at"] or "", reverse=True)
    return {"sessions": result}


@router.get("/session/{session_id}")
async def get_session_state(session_id: str):
    """Return current session state for graph positioning."""
    session = await session_service.get_session(session_id)
    if not session:
        return {"error": "Session not found", "session_id": session_id}

    return {
        "session_id": session_id,
        "question_id": session.tutoring.question_id,
        "current_node_id": session.tutoring.current_node_id,
        "depth": session.tutoring.depth,
        "is_new_branch": session.tutoring.is_new_branch,
        "original_query": session.original_query,
    }


@router.websocket("/ws/{session_id}")
async def graph_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time graph updates."""
    await websocket.accept()
    queue = await event_bus.subscribe(session_id)

    logger.info(
        "Graph WebSocket connected",
        context={"session_id": session_id},
    )

    try:
        # Send initial session state
        session = await session_service.get_session(session_id)
        if session and session.tutoring.question_id:
            tree_data = await get_tree(session.tutoring.question_id)
            await websocket.send_json(
                {
                    "type": "session_start",
                    "question_id": session.tutoring.question_id,
                    "current_node_id": session.tutoring.current_node_id,
                    "depth": session.tutoring.depth,
                    "tree": tree_data,
                }
            )

        # Listen for events and forward to client
        while True:
            try:
                event = await asyncio.wait_for(
                    queue.get(),
                    timeout=Config.DASHBOARD.WS_HEARTBEAT_SECONDS,
                )
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                await websocket.send_json({"type": "heartbeat"})

    except WebSocketDisconnect:
        logger.info(
            "Graph WebSocket disconnected",
            context={"session_id": session_id},
        )
    except Exception as e:
        logger.error(
            "Graph WebSocket error",
            context={"session_id": session_id, "error": str(e)},
        )
    finally:
        event_bus.unsubscribe(session_id, queue)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve the graph visualization dashboard as inline HTML."""
    return DASHBOARD_HTML


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tutoring Graph</title>
<script src="https://unpkg.com/cytoscape@3.30.4/dist/cytoscape.min.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0f1117;
    color: #e0e0e0;
    height: 100vh;
    display: flex;
    flex-direction: column;
  }
  #header {
    padding: 10px 16px;
    background: #1a1b26;
    border-bottom: 1px solid #2a2b36;
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
  }
  #header h1 {
    font-size: 14px;
    font-weight: 600;
    color: #7aa2f7;
  }
  #status {
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 10px;
    background: #2a2b36;
  }
  #status.connected { background: #1a3a2a; color: #9ece6a; }
  #status.disconnected { background: #3a1a1a; color: #f7768e; }
  #status.waiting { background: #2a2520; color: #e0af68; }
  #cy {
    flex: 1;
    min-height: 0;
    position: relative;
  }
  #event-log {
    height: 140px;
    overflow-y: auto;
    background: #1a1b26;
    border-top: 1px solid #2a2b36;
    padding: 8px 12px;
    font-size: 11px;
    font-family: 'Fira Code', 'Cascadia Code', monospace;
    flex-shrink: 0;
  }
  .log-entry {
    padding: 2px 0;
    border-bottom: 1px solid #1f2030;
  }
  .log-entry .time { color: #565f89; }
  .log-entry .type { font-weight: 600; }
  .type-cache_search { color: #e0af68; }
  .type-cache_hit { color: #9ece6a; }
  .type-cache_miss { color: #f7768e; }
  .type-node_created { color: #7dcfff; }
  .type-intent_classified { color: #bb9af7; }
  .type-position_update { color: #7aa2f7; }
  .type-session_start { color: #73daca; }
  .type-correction { color: #ff9e64; }
  .type-session_created { color: #73daca; }
  .type-question_reused { color: #9ece6a; }

  #tooltip {
    display: none;
    position: absolute;
    background: #24283b;
    border: 1px solid #3b4261;
    border-radius: 6px;
    padding: 10px 14px;
    max-width: 320px;
    font-size: 12px;
    z-index: 1000;
    pointer-events: none;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  }
  #tooltip .tt-label { color: #7aa2f7; font-weight: 600; margin-bottom: 4px; }
  #tooltip .tt-text { color: #a9b1d6; line-height: 1.4; }
  #tooltip .tt-depth { color: #565f89; font-size: 11px; margin-top: 4px; }

  #session-picker {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    text-align: center;
    color: #a9b1d6;
    width: 90%;
    max-width: 500px;
  }
  #session-picker h2 {
    font-size: 16px;
    color: #7aa2f7;
    margin-bottom: 16px;
  }
  #session-picker .subtitle {
    font-size: 12px;
    color: #565f89;
    margin-bottom: 20px;
  }
  #session-list {
    text-align: left;
    max-height: 300px;
    overflow-y: auto;
  }
  .session-card {
    background: #1a1b26;
    border: 1px solid #2a2b36;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 8px;
    cursor: pointer;
    transition: border-color 0.2s, background 0.2s;
  }
  .session-card:hover {
    border-color: #7aa2f7;
    background: #1f2030;
  }
  .session-card .query {
    font-size: 13px;
    color: #c0caf5;
    margin-bottom: 4px;
  }
  .session-card .meta {
    font-size: 11px;
    color: #565f89;
  }
  .no-sessions {
    color: #565f89;
    font-size: 13px;
    padding: 20px;
  }
  .spinner {
    width: 32px; height: 32px;
    border: 3px solid #2a2b36;
    border-top-color: #7aa2f7;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin: 0 auto 12px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
  .auto-refresh {
    font-size: 11px;
    color: #565f89;
    margin-top: 12px;
  }
  .auto-refresh .dot {
    display: inline-block;
    width: 6px; height: 6px;
    border-radius: 50%;
    background: #e0af68;
    animation: pulse 2s infinite;
    margin-right: 4px;
    vertical-align: middle;
  }
</style>
</head>
<body>
<div id="header">
  <h1>Tutoring Graph</h1>
  <span id="status" class="disconnected">Disconnected</span>
  <span id="session-info" style="font-size:11px;color:#565f89;margin-left:auto;"></span>
</div>
<div id="cy">
  <div id="session-picker" style="display:none;">
    <h2>Tutoring Graph Visualizer</h2>
    <div class="subtitle">Select an active tutoring session or start chatting to create one</div>
    <div id="session-list"></div>
    <div class="auto-refresh"><span class="dot"></span>Auto-refreshing every 3 seconds</div>
  </div>
</div>
<div id="tooltip">
  <div class="tt-label"></div>
  <div class="tt-text"></div>
  <div class="tt-depth"></div>
</div>
<div id="event-log"></div>

<script>
const params = new URLSearchParams(window.location.search);
let sessionId = params.get('session_id') || '';

const statusEl = document.getElementById('status');
const sessionInfoEl = document.getElementById('session-info');
const logEl = document.getElementById('event-log');
const pickerEl = document.getElementById('session-picker');
const sessionListEl = document.getElementById('session-list');
const tooltipEl = document.getElementById('tooltip');

let cy = null;
let currentNodeId = null;
let ws = null;
let pollInterval = null;
let knownSessionCount = 0;

function initCy() {
  if (cy) return;
  pickerEl.style.display = 'none';
  cy = cytoscape({
    container: document.getElementById('cy'),
    style: [
      {
        selector: 'node',
        style: {
          'label': 'data(label)',
          'text-wrap': 'wrap',
          'text-max-width': '120px',
          'font-size': '10px',
          'color': '#a9b1d6',
          'text-valign': 'bottom',
          'text-margin-y': 6,
          'background-color': '#3b4261',
          'border-width': 2,
          'border-color': '#565f89',
          'width': 36,
          'height': 36,
        }
      },
      {
        selector: 'node[type="root"]',
        style: {
          'background-color': '#7aa2f7',
          'border-color': '#7aa2f7',
          'width': 44,
          'height': 44,
          'font-size': '11px',
          'font-weight': 'bold',
          'color': '#c0caf5',
        }
      },
      {
        selector: 'node.current',
        style: {
          'background-color': '#9ece6a',
          'border-color': '#9ece6a',
          'border-width': 3,
        }
      },
      {
        selector: 'node.cache-hit',
        style: {
          'background-color': '#e0af68',
          'border-color': '#e0af68',
        }
      },
      {
        selector: 'node.cache-miss',
        style: {
          'border-color': '#f7768e',
          'border-width': 3,
          'border-style': 'dashed',
        }
      },
      {
        selector: 'node.search-area',
        style: {
          'border-color': '#e0af68',
          'border-width': 3,
          'border-style': 'dashed',
        }
      },
      {
        selector: 'node.new-node',
        style: {
          'background-color': '#7dcfff',
          'border-color': '#7dcfff',
        }
      },
      {
        selector: 'edge',
        style: {
          'width': 2,
          'line-color': '#3b4261',
          'target-arrow-color': '#3b4261',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
          'arrow-scale': 0.8,
        }
      },
      {
        selector: 'edge.active-path',
        style: {
          'line-color': '#9ece6a',
          'target-arrow-color': '#9ece6a',
          'width': 3,
        }
      },
    ],
    layout: { name: 'breadthfirst', directed: true, spacingFactor: 1.5, padding: 30 },
    elements: [],
    userZoomingEnabled: true,
    userPanningEnabled: true,
  });

  cy.on('mouseover', 'node', function(e) {
    var node = e.target;
    var data = node.data();
    tooltipEl.querySelector('.tt-label').textContent = data.type === 'root' ? 'Question' : 'Interaction';
    tooltipEl.querySelector('.tt-text').textContent = data.full_text || data.label;
    tooltipEl.querySelector('.tt-depth').textContent = data.type === 'root' ? '' : 'Depth: ' + data.depth;
    tooltipEl.style.display = 'block';
    var pos = e.renderedPosition;
    var container = document.getElementById('cy').getBoundingClientRect();
    tooltipEl.style.left = (container.left + pos.x + 15) + 'px';
    tooltipEl.style.top = (container.top + pos.y - 10) + 'px';
  });

  cy.on('mouseout', 'node', function() {
    tooltipEl.style.display = 'none';
  });
}

function addLog(type, message) {
  var now = new Date().toLocaleTimeString('en-US', { hour12: false });
  var entry = document.createElement('div');
  entry.className = 'log-entry';
  entry.innerHTML = '<span class="time">' + now + '</span> '
    + '<span class="type type-' + type + '">[' + type + ']</span> '
    + message;
  logEl.prepend(entry);
  while (logEl.children.length > 50) logEl.removeChild(logEl.lastChild);
}

function loadTree(treeData) {
  if (!cy) initCy();
  cy.elements().remove();
  if (treeData.nodes && treeData.nodes.length > 0) {
    cy.add(treeData.nodes);
    cy.add(treeData.edges);
    cy.layout({ name: 'breadthfirst', directed: true, spacingFactor: 1.5, padding: 30 }).run();
  }
}

function highlightCurrent(nodeId) {
  if (!cy) return;
  cy.nodes('.current').removeClass('current');
  cy.edges('.active-path').removeClass('active-path');
  if (!nodeId) return;
  currentNodeId = nodeId;
  var node = cy.getElementById(nodeId);
  if (node.length) {
    node.addClass('current');
    var cur = node;
    while (cur.length) {
      var incomers = cur.incomers('edge');
      if (incomers.length === 0) break;
      incomers.addClass('active-path');
      cur = incomers.sources();
    }
  }
}

function clearTempClasses() {
  if (!cy) return;
  cy.nodes('.search-area').removeClass('search-area');
  cy.nodes('.cache-hit').removeClass('cache-hit');
  cy.nodes('.cache-miss').removeClass('cache-miss');
  cy.nodes('.new-node').removeClass('new-node');
}

function handleEvent(event) {
  if (event.type === 'heartbeat') return;
  switch (event.type) {
    case 'session_start':
      sessionInfoEl.textContent = 'Q: ' + (event.question_id || '').substring(0, 8) + '...';
      if (event.tree) loadTree(event.tree);
      highlightCurrent(event.current_node_id);
      addLog(event.type, 'Session loaded — depth: ' + (event.depth || 0));
      break;
    case 'session_created':
      sessionInfoEl.textContent = 'Q: ' + (event.question_id || '').substring(0, 8) + '...';
      if (event.reused_question && event.question_id) {
        addLog('question_reused', 'Reused existing question (similarity: ' + (event.confidence || 0).toFixed(3) + ') — loading existing tree');
        fetch('/graph/tree/' + event.question_id)
          .then(function(r) { return r.json(); })
          .then(function(data) { loadTree(data); })
          .catch(function() {});
      } else {
        if (event.tree) loadTree(event.tree);
      }
      highlightCurrent(event.current_node_id);
      addLog(event.type, 'Session started — source: ' + (event.source || 'unknown') + ', confidence: ' + (event.confidence || 0).toFixed(3));
      break;
    case 'cache_search':
      clearTempClasses();
      if (cy) {
        var pid = event.parent_id || event.question_id;
        var p = cy.getElementById(pid);
        if (p.length) p.outgoers('node').addClass('search-area');
      }
      addLog('cache_search', 'Searching children of ' + ((event.parent_id || 'root').substring(0, 8)));
      break;
    case 'cache_hit':
      clearTempClasses();
      if (cy && event.matched_node_id) cy.getElementById(event.matched_node_id).addClass('cache-hit');
      addLog('cache_hit', 'Hit node ' + (event.matched_node_id || '').substring(0, 8) + ' (score: ' + (event.score || 0).toFixed(2) + ')');
      break;
    case 'cache_miss':
      if (cy) {
        cy.nodes('.search-area').removeClass('search-area').addClass('cache-miss');
        setTimeout(function() { if (cy) cy.nodes('.cache-miss').removeClass('cache-miss'); }, 2000);
      }
      addLog('cache_miss', 'No cached match found');
      break;
    case 'intent_classified':
      addLog('intent_classified', event.intent + ' (confidence: ' + (event.confidence || 0).toFixed(2) + ')');
      break;
    case 'node_created':
      if (cy && event.node_id) {
        var npid = event.parent_id || event.question_id;
        var ui = event.user_input || '';
        var lbl = ui.length > 40 ? ui.substring(0, 40) + '...' : ui;
        cy.add([
          { data: { id: event.node_id, label: lbl, full_text: ui, type: 'interaction', depth: event.depth || 1 } },
          { data: { source: npid, target: event.node_id } }
        ]);
        cy.getElementById(event.node_id).addClass('new-node');
        cy.layout({ name: 'breadthfirst', directed: true, spacingFactor: 1.5, padding: 30, animate: true, animationDuration: 300 }).run();
        setTimeout(function() { if (cy) cy.getElementById(event.node_id).removeClass('new-node'); }, 1500);
      }
      addLog('node_created', 'New node at depth ' + (event.depth || '?'));
      break;
    case 'position_update':
      highlightCurrent(event.current_node_id);
      addLog('position_update', 'Moved to depth ' + (event.depth || '?'));
      break;
    case 'correction':
      addLog('correction', 'Question corrected — reloading graph');
      if (event.question_id) {
        sessionInfoEl.textContent = 'Q: ' + event.question_id.substring(0, 8) + '...';
        setTimeout(function() {
          fetch('/graph/tree/' + event.question_id)
            .then(function(r) { return r.json(); })
            .then(function(data) { loadTree(data); })
            .catch(function() {});
        }, 500);
      }
      break;
    default:
      addLog(event.type || 'unknown', JSON.stringify(event).substring(0, 100));
  }
}

function connectToSession(sid) {
  sessionId = sid;
  if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }

  var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  var wsUrl = protocol + '//' + window.location.host + '/graph/ws/' + sid;

  ws = new WebSocket(wsUrl);
  ws.onopen = function() {
    statusEl.textContent = 'Connected';
    statusEl.className = 'connected';
    addLog('session_start', 'Connected to session ' + sid.substring(0, 8) + '...');
  };
  ws.onmessage = function(e) {
    try { handleEvent(JSON.parse(e.data)); } catch (err) { console.error('Parse error:', err); }
  };
  ws.onclose = function() {
    statusEl.textContent = 'Disconnected';
    statusEl.className = 'disconnected';
    addLog('session_start', 'Disconnected — reconnecting in 3s...');
    setTimeout(function() { connectToSession(sid); }, 3000);
  };
  ws.onerror = function(err) { console.error('WebSocket error:', err); };
}

function selectSession(sid) {
  pickerEl.style.display = 'none';
  connectToSession(sid);
  // Update URL without reload
  var url = new URL(window.location);
  url.searchParams.set('session_id', sid);
  window.history.replaceState({}, '', url);
}

function renderSessions(sessions) {
  sessionListEl.innerHTML = '';
  if (!sessions.length) {
    sessionListEl.innerHTML = '<div class="no-sessions">No active tutoring sessions.<br>Start a math conversation in the chat to create one.</div>';
    return;
  }
  sessions.forEach(function(s) {
    var card = document.createElement('div');
    card.className = 'session-card';
    var query = s.original_query || 'Unknown question';
    if (query.length > 80) query = query.substring(0, 80) + '...';
    card.innerHTML = '<div class="query">' + query + '</div>'
      + '<div class="meta">Session: ' + s.session_id.substring(0, 8) + '... | Depth: ' + s.depth + '</div>';
    card.onclick = function() { selectSession(s.session_id); };
    sessionListEl.appendChild(card);
  });
}

function fetchSessions() {
  fetch('/graph/sessions')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var sessions = data.sessions || [];
      renderSessions(sessions);
      // Auto-connect if a new session appeared (user just started chatting)
      if (sessions.length > knownSessionCount && knownSessionCount > 0) {
        selectSession(sessions[0].session_id);
      }
      knownSessionCount = sessions.length;
    })
    .catch(function() {
      sessionListEl.innerHTML = '<div class="no-sessions">Could not reach the server.</div>';
    });
}

function showSessionPicker() {
  pickerEl.style.display = 'block';
  statusEl.textContent = 'Waiting';
  statusEl.className = 'waiting';
  fetchSessions();
  pollInterval = setInterval(fetchSessions, 3000);
}

// Entry point
if (sessionId) {
  connectToSession(sessionId);
} else {
  showSessionPicker();
}
</script>
</body>
</html>
"""
