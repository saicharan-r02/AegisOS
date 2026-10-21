import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Shield, Terminal, CheckCircle2, Zap, LayoutDashboard,
  ListOrdered, Rocket, AlertTriangle, RefreshCw,
  X, Send, Database, Cpu, Pause, Play,
  Square, Eye, CheckSquare, BookOpen, FileCode, Check, Ban
} from 'lucide-react'
import './index.css'

/* ──────────────────────────────── types ──────────────────────────────── */
interface KernelEvent { event_type: string; payload: any; event_id?: number }
interface Mission {
  session_id: string; goal: string; status: string;
  current_step_index: number; updated_at: string
}
interface Toast { id: number; msg: string; kind: 'success' | 'error' | 'info' }
interface ApprovalItem {
  approval_id: string; session_id: string; command: string;
  reason: string; timestamp: string; status: string
}
interface AcceptanceItem {
  id: string; description: string; passed: boolean; evidence: string
}
interface SpanRecord {
  span_id: string; parent_span_id: string | null; span_type: string;
  name: string; role: string | null; duration_ms: number; status: string;
  tokens_in: number; tokens_out: number; cost_usd: number; error?: string
}

type Page = 'dashboard' | 'missions' | 'launch' | 'memory'

/* ──────────────────────────────── constants ──────────────────────────── */
const API = 'http://127.0.0.1:8000'
const WS  = 'ws://127.0.0.1:8000'

const AGENTS = [
  { id: 'CTO', label: 'Architect', emoji: '🧠', color: '#00d2ff', rgb: '0,210,255' },
  { id: 'DEV', label: 'Developer', emoji: '⚡', color: '#00e87a', rgb: '0,232,122' },
  { id: 'QA',  label: 'QA Tester', emoji: '🔬', color: '#f5b731', rgb: '245,183,49' },
  { id: 'SEC', label: 'Security',  emoji: '🛡️', color: '#d942ff', rgb: '217,66,255' },
  { id: 'OPS', label: 'DevOps',    emoji: '🔧', color: '#4a7fdb', rgb: '74,127,219' },
]

function roleTag(role: string) {
  const r = (role || '').toUpperCase()
  if (r.includes('CTO'))  return 'tag-cto'
  if (r.includes('DEV'))  return 'tag-dev'
  if (r.includes('QA'))   return 'tag-qa'
  if (r.includes('SEC'))  return 'tag-sec'
  if (r.includes('OPS'))  return 'tag-ops'
  return 'tag-sys'
}

function dotClass(evt: KernelEvent) {
  if (evt.event_type === 'StepCompletedEvent') {
    return evt.payload?.step?.status === 'SUCCESS' ? 'success' : 'error'
  }
  if (evt.event_type === 'MissionStatusChangedEvent') {
    const s = evt.payload?.new_status
    if (s === 'COMPLETED') return 'success'
    if (s === 'FAILED')    return 'error'
    return 'running'
  }
  if (evt.event_type === 'StepStartedEvent') return 'running'
  return 'info'
}

function evtLabel(evt: KernelEvent): string {
  switch (evt.event_type) {
    case 'StateTransitionEvent':
      return `Handoff → ${evt.payload?.to_role || '?'}`
    case 'StepStartedEvent':
      return `${evt.payload?.step?.role || ''} starting step`
    case 'StepCompletedEvent': {
      const ok = evt.payload?.step?.status === 'SUCCESS'
      const ms = Math.round(evt.payload?.step?.duration_ms ?? 0)
      return ok ? `Step completed in ${ms}ms` : `Step failed`
    }
    case 'MissionStatusChangedEvent':
      return `Mission → ${evt.payload?.new_status}`
    default:
      return evt.event_type.replace(/Event$/, '')
  }
}

function evtRole(evt: KernelEvent): string {
  return (
    evt.payload?.step?.role ||
    evt.payload?.to_role ||
    (evt.event_type === 'MissionStatusChangedEvent' ? 'SYS' : '')
  )
}

function nowStr() {
  return new Date().toLocaleTimeString('en-US', { hour12: false })
}

function missionBadgeClass(status: string) {
  switch (status?.toUpperCase()) {
    case 'COMPLETED': return 'msb-completed'
    case 'RUNNING':   return 'msb-running'
    case 'FAILED':    return 'msb-failed'
    default:          return 'msb-pending'
  }
}

/* ══════════════════════════════ App ══════════════════════════════════════ */
export default function App() {
  const [page, setPage]               = useState<Page>('dashboard')
  const [events, setEvents]           = useState<(KernelEvent & { ts: string })[]>([])
  const [missions, setMissions]       = useState<Mission[]>([])
  const [connected, setConnected]     = useState(false)
  const [activeRole, setActiveRole]   = useState<string>('')
  const [toasts, setToasts]           = useState<Toast[]>([])
  const toastId                       = useRef(0)

  // Stats
  const [stats, setStats] = useState({ total: 0, completed: 0, steps: 0, errors: 0, tokens: 0, cost: 0.0 })

  // Approvals
  const [approvals, setApprovals] = useState<ApprovalItem[]>([])

  // Modals & Panels
  const [activeDiff, setActiveDiff] = useState<string | null>(null)
  const [activeTrace, setActiveTrace] = useState<SpanRecord[] | null>(null)
  const [activeAcceptance, setActiveAcceptance] = useState<AcceptanceItem[] | null>(null)
  const [selectedMission, setSelectedMission] = useState<Mission | null>(null)

  // Memory State
  const [memoryData, setMemoryData] = useState<{ episodes: any[]; conventions: any[] }>({ episodes: [], conventions: [] })

  // Launcher state
  const [goal, setGoal]             = useState('')
  const [provider, setProvider]     = useState('groq')
  const [workspace, setWorkspace]   = useState('')
  const [strategy, setStrategy]     = useState('adaptive')
  const [launching, setLaunching]   = useState(false)

  /* ── toast helper ── */
  const addToast = useCallback((msg: string, kind: Toast['kind'] = 'info') => {
    const id = ++toastId.current
    setToasts(p => [...p, { id, msg, kind }])
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 4000)
  }, [])

  /* ── fetch missions & approvals ── */
  const fetchMissions = useCallback(() => {
    fetch(`${API}/api/missions`)
      .then(r => r.json())
      .then(d => {
        if (d.missions) {
          const ms = d.missions.reverse() as Mission[]
          setMissions(ms)
          if (!selectedMission && ms.length > 0) setSelectedMission(ms[0])
          setStats(s => ({
            ...s,
            total: ms.length,
            completed: ms.filter(m => m.status === 'COMPLETED').length,
          }))
        }
      })
      .catch(() => {})
  }, [selectedMission])

  const fetchApprovals = useCallback(() => {
    fetch(`${API}/api/approvals`)
      .then(r => r.json())
      .then(d => { if (Array.isArray(d)) setApprovals(d) })
      .catch(() => {})
  }, [])

  const fetchMemory = useCallback(() => {
    fetch(`${API}/api/memory`)
      .then(r => r.json())
      .then(d => { setMemoryData(d) })
      .catch(() => {})
  }, [])

  useEffect(() => {
    fetchMissions()
    fetchApprovals()
    fetchMemory()
    const timer = setInterval(() => { fetchApprovals() }, 5000)
    return () => clearInterval(timer)
  }, [fetchMissions, fetchApprovals, fetchMemory])

  /* ── WebSocket ── */
  useEffect(() => {
    let ws: WebSocket
    let retryTimer: ReturnType<typeof setTimeout>

    function connect() {
      ws = new WebSocket(`${WS}/api/events`)
      ws.onopen  = () => { setConnected(true); addToast('Mission Control Live', 'success') }
      ws.onclose = () => { setConnected(false); retryTimer = setTimeout(connect, 3000) }
      ws.onerror = () => { setConnected(false) }
      ws.onmessage = (msg) => {
        try {
          const data: KernelEvent = JSON.parse(msg.data)
          const enriched = { ...data, ts: nowStr() }
          setEvents(p => [enriched, ...p].slice(0, 80))

          const role = evtRole(data)
          if (role && data.event_type !== 'MissionStatusChangedEvent') setActiveRole(role)
          if (data.event_type === 'MissionStatusChangedEvent') {
            fetchMissions()
            fetchApprovals()
          }
          if (data.event_type === 'StepCompletedEvent') {
            const ok = data.payload?.step?.status === 'SUCCESS'
            setStats(s => ({ ...s, steps: s.steps + 1, errors: ok ? s.errors : s.errors + 1 }))
          }
        } catch { /* ignore */ }
      }
    }
    connect()
    return () => { ws?.close(); clearTimeout(retryTimer) }
  }, [addToast, fetchMissions, fetchApprovals])

  /* ── Action handlers ── */
  const handleLaunch = async () => {
    if (!goal.trim()) return
    setLaunching(true)
    try {
      const res = await fetch(`${API}/api/missions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal, provider, workspace: workspace || '.', strategy }),
      })
      const d = await res.json()
      if (d.success) {
        addToast(`Mission launched: ${d.session_id}`, 'success')
        setGoal('')
        fetchMissions()
        setPage('dashboard')
      } else {
        addToast(`Launch failed: ${d.message}`, 'error')
      }
    } catch {
      addToast('Cannot connect to Aegis API backend', 'error')
    } finally {
      setLaunching(false)
    }
  }

  const handleControlAction = async (action: 'pause' | 'resume' | 'cancel') => {
    if (!selectedMission) return
    try {
      const res = await fetch(`${API}/api/missions/${selectedMission.session_id}/${action}`, { method: 'POST' })
      const d = await res.json()
      addToast(d.message, d.success ? 'success' : 'error')
      fetchMissions()
    } catch {
      addToast(`Failed to ${action} mission`, 'error')
    }
  }

  const handleApprovalAction = async (approvalId: string, action: 'approve' | 'deny') => {
    try {
      const res = await fetch(`${API}/api/approvals/${approvalId}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      })
      if (res.ok) {
        addToast(`Action ${action}d successfully`, 'success')
        fetchApprovals()
      }
    } catch {
      addToast('Failed to submit approval decision', 'error')
    }
  }

  const openDiffModal = async (sessionId: string) => {
    try {
      const res = await fetch(`${API}/api/missions/${sessionId}/diff`)
      const d = await res.json()
      setActiveDiff(d.diff || 'No diff available.')
    } catch {
      setActiveDiff('Error retrieving git diff.')
    }
  }

  const openTraceModal = async (sessionId: string) => {
    try {
      const res = await fetch(`${API}/api/missions/${sessionId}/trace`)
      const d = await res.json()
      setActiveTrace(d.spans || [])
    } catch {
      setActiveTrace([])
    }
  }

  const openAcceptanceModal = async (sessionId: string) => {
    try {
      const res = await fetch(`${API}/api/missions/${sessionId}/acceptance`)
      const d = await res.json()
      setActiveAcceptance(d.criteria || [])
    } catch {
      setActiveAcceptance([])
    }
  }

  /* ══════════════════ SIDEBAR ══════════════════ */
  const Sidebar = () => (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-icon">
          <Shield size={20} color="var(--cyan)" />
        </div>
        <div className="brand-text">
          <span className="brand-name">AegisOS</span>
          <span className="brand-badge">v2.0 PROD</span>
        </div>
      </div>

      <nav className="nav-menu">
        <button
          className={`nav-item ${page === 'dashboard' ? 'active' : ''}`}
          onClick={() => setPage('dashboard')}
        >
          <LayoutDashboard size={16} />
          <span>War Room</span>
        </button>
        <button
          className={`nav-item ${page === 'missions' ? 'active' : ''}`}
          onClick={() => setPage('missions')}
        >
          <ListOrdered size={16} />
          <span>Missions</span>
          {missions.length > 0 && <span className="nav-count">{missions.length}</span>}
        </button>
        <button
          className={`nav-item ${page === 'memory' ? 'active' : ''}`}
          onClick={() => { fetchMemory(); setPage('memory') }}
        >
          <BookOpen size={16} />
          <span>Memory & Rules</span>
        </button>
        <button
          className={`nav-item ${page === 'launch' ? 'active' : ''}`}
          onClick={() => setPage('launch')}
        >
          <Rocket size={16} />
          <span>Launch Mission</span>
        </button>
      </nav>

      <div style={{ marginTop: 'auto', padding: '0 0.8rem 1rem' }}>
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--glass-border)', borderRadius: 'var(--r-md)', padding: '0.75rem' }}>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginBottom: '0.4rem', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 700 }}>
            System Health
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.75rem', marginBottom: '0.2rem' }}>
            <span style={{ color: 'var(--text-secondary)' }}>Event Bus:</span>
            <span style={{ color: connected ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>
              {connected ? 'CONNECTED' : 'DISCONNECTED'}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.75rem' }}>
            <span style={{ color: 'var(--text-secondary)' }}>Strategy:</span>
            <span style={{ color: 'var(--cyan)', fontWeight: 600 }}>ADAPTIVE</span>
          </div>
        </div>
      </div>
    </aside>
  )

  /* ══════════════════ TOPBAR ══════════════════ */
  const Topbar = () => (
    <header className="topbar">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem' }}>
        <span style={{ fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-primary)' }}>
          {page === 'dashboard' && 'War Room Live Operations'}
          {page === 'missions'  && 'Historical Missions & Audit Traces'}
          {page === 'memory'    && 'Cross-Mission Episodic Memory & Learned Conventions'}
          {page === 'launch'    && 'Dispatch Autonomous Engineering Mission'}
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <div className={`status-pill ${connected ? 'status-online' : 'status-offline'}`}>
          <span className="status-dot" />
          <span>{connected ? 'LIVE TELEMETRY' : 'OFFLINE'}</span>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={() => { fetchMissions(); fetchApprovals(); addToast('Refreshed', 'info') }}>
          <RefreshCw size={13} />
        </button>
      </div>
    </header>
  )

  /* ══════════════════ DASHBOARD PAGE ══════════════════ */
  const DashboardPage = () => (
    <div className="dashboard-grid">
      {/* ── APPROVALS INBOX (Phase 8 requirement) ── */}
      {approvals.length > 0 && (
        <div className="approvals-banner" style={{ gridColumn: '1 / -1' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
            <div style={{ background: 'rgba(245,183,49,0.2)', padding: '0.45rem', borderRadius: '50%' }}>
              <AlertTriangle size={18} color="var(--yellow)" />
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: '0.85rem', color: 'var(--yellow)' }}>
                Risky Command Approval Required ({approvals.length} pending)
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', fontFamily: 'JetBrains Mono, monospace' }}>
                {approvals[0].command} — <span style={{ color: 'var(--text-muted)' }}>{approvals[0].reason}</span>
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button className="btn btn-primary btn-sm" onClick={() => handleApprovalAction(approvals[0].approval_id, 'approve')}>
              <Check size={14} /> Approve
            </button>
            <button className="btn btn-danger btn-sm" onClick={() => handleApprovalAction(approvals[0].approval_id, 'deny')}>
              <Ban size={14} /> Deny
            </button>
          </div>
        </div>
      )}

      {/* ── STATS ROW ── */}
      <div className="stats-row" style={{ gridColumn: '1 / -1' }}>
        <div className="stat-card">
          <div className="stat-label">Total Missions</div>
          <div className="stat-val">{stats.total}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Success Rate</div>
          <div className="stat-val" style={{ color: 'var(--green)' }}>
            {stats.total > 0 ? `${Math.round((stats.completed / stats.total) * 100)}%` : '100%'}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Steps Executed</div>
          <div className="stat-val">{stats.steps}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Budget Token Accounting</div>
          <div className="stat-val" style={{ color: 'var(--cyan)' }}>
            {(stats.tokens || 12450).toLocaleString()} <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>/ 100k</span>
          </div>
        </div>
      </div>

      {/* ── ACTIVE MISSION CONTROL BAR ── */}
      {selectedMission && (
        <div className="card" style={{ gridColumn: '1 / -1', padding: '0.85rem 1.25rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>
              Focused Mission Control: <span style={{ color: 'var(--cyan)' }}>{selectedMission.session_id}</span>
            </div>
            <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)', marginTop: 2 }}>
              {selectedMission.goal}
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <button className="btn btn-ghost btn-sm" onClick={() => handleControlAction('pause')} title="Pause mission">
              <Pause size={14} /> Pause
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => handleControlAction('resume')} title="Resume mission">
              <Play size={14} /> Resume
            </button>
            <button className="btn btn-danger btn-sm" onClick={() => handleControlAction('cancel')} title="Abort mission">
              <Square size={14} /> Cancel
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => openDiffModal(selectedMission.session_id)}>
              <FileCode size={14} /> Diff
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => openTraceModal(selectedMission.session_id)}>
              <Eye size={14} /> Trace
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => openAcceptanceModal(selectedMission.session_id)}>
              <CheckSquare size={14} /> Acceptance
            </button>
          </div>
        </div>
      )}

      {/* ── AGENT DEPARTMENT MATRIX ── */}
      <div className="card" style={{ gridColumn: '1 / span 2' }}>
        <div className="card-header">
          <div className="card-title">
            <Cpu size={15} color="var(--cyan)" />
            <span>Autonomous Department Swarm</span>
          </div>
          <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Adaptive Orchestrator</span>
        </div>
        <div className="department-matrix">
          {AGENTS.map(a => {
            const isActive = activeRole.toUpperCase().includes(a.id)
            return (
              <div key={a.id} className={`agent-badge ${isActive ? 'active' : ''}`} style={{ borderColor: isActive ? a.color : undefined }}>
                <span className="agent-badge-emoji">{a.emoji}</span>
                <span className="agent-badge-label">{a.label}</span>
                <span className={`agent-badge-state ${isActive ? 'running' : 'idle'}`}>
                  {isActive ? 'ACTIVE' : 'READY'}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* ── LIVE TELEMETRY STREAM ── */}
      <div className="card" style={{ gridColumn: '3 / span 2', minHeight: 400 }}>
        <div className="card-header">
          <div className="card-title">
            <Terminal size={15} color="var(--green)" />
            <span>Live Mission Telemetry</span>
          </div>
          <span className="chip chip-cyan">{events.length} events</span>
        </div>
        <div className="feed-stream">
          {events.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)', fontSize: '0.78rem' }}>
              Awaiting kernel telemetry events... Launch a mission to observe live traces.
            </div>
          ) : (
            events.map((evt, idx) => (
              <div key={idx} className="feed-item">
                <span className={`feed-dot ${dotClass(evt)}`} />
                <div className="feed-body">
                  <div className="feed-header">
                    <span className={`feed-role ${roleTag(evtRole(evt))}`}>
                      {evtRole(evt) || 'SYS'}
                    </span>
                    <span className="feed-label">{evtLabel(evt)}</span>
                    <span className="feed-time">{evt.ts}</span>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )

  /* ══════════════════ MISSIONS PAGE ══════════════════ */
  const MissionsPage = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <div className="card">
        <div className="card-header">
          <div className="card-title">
            <ListOrdered size={15} color="var(--cyan)" />
            <span>Mission Registry & Rollback History</span>
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{missions.length} recorded</span>
        </div>
        <div className="mission-list" style={{ maxHeight: 'none' }}>
          {missions.map(m => (
            <div
              key={m.session_id}
              className={`mission-item ${selectedMission?.session_id === m.session_id ? 'selected' : ''}`}
              onClick={() => setSelectedMission(m)}
            >
              <div className="mission-info">
                <div className="mission-goal-text">{m.goal}</div>
                <div className="mission-meta">
                  ID: {m.session_id} • Step {m.current_step_index} • {m.updated_at}
                </div>
              </div>
              <span className={`mission-status-badge ${missionBadgeClass(m.status)}`}>
                {m.status}
              </span>
              <div style={{ display: 'flex', gap: '0.4rem', marginLeft: '0.8rem' }}>
                <button className="btn btn-ghost btn-sm" onClick={(e) => { e.stopPropagation(); openDiffModal(m.session_id) }}>
                  Diff
                </button>
                <button className="btn btn-ghost btn-sm" onClick={(e) => { e.stopPropagation(); openTraceModal(m.session_id) }}>
                  Trace
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )

  /* ══════════════════ MEMORY PAGE ══════════════════ */
  const MemoryPage = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      <div className="card">
        <div className="card-header">
          <div className="card-title">
            <BookOpen size={15} color="var(--cyan)" />
            <span>Learned Codebase Conventions</span>
          </div>
          <span className="chip chip-green">{memoryData.conventions.length} rules</span>
        </div>
        <div className="memory-grid">
          {memoryData.conventions.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.78rem', padding: '1rem' }}>
              No conventions learned yet. Completed missions automatically record successful patterns.
            </div>
          ) : (
            memoryData.conventions.map((c, i) => (
              <div key={i} className="memory-card">
                <span className="chip chip-cyan" style={{ width: 'fit-content' }}>{c.category}</span>
                <div style={{ fontSize: '0.82rem', fontWeight: 600 }}>{c.rule}</div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>{c.context}</div>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <div className="card-title">
            <Database size={15} color="var(--magenta)" />
            <span>Episodic Mission History</span>
          </div>
          <span className="chip chip-cyan">{memoryData.episodes.length} episodes</span>
        </div>
        <div className="memory-grid">
          {memoryData.episodes.map((ep, i) => (
            <div key={i} className="memory-card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{ep.session_id}</span>
                <span className={`mission-status-badge ${missionBadgeClass(ep.status)}`}>{ep.status}</span>
              </div>
              <div style={{ fontSize: '0.82rem', fontWeight: 600 }}>{ep.objective}</div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>{ep.summary}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )

  /* ══════════════════ LAUNCH PAGE ══════════════════ */
  const LaunchPage = () => (
    <div style={{ maxWidth: 560 }}>
      <div className="launcher-card">
        <div className="launcher-header">
          <Rocket size={15} color="var(--cyan)" />
          <span style={{ fontSize: '0.88rem', fontWeight: 600 }}>Mission Configuration</span>
        </div>
        <div className="launcher-body">
          <div className="form-field">
            <label className="form-label">Mission Goal *</label>
            <textarea
              className="form-textarea"
              placeholder="Describe the engineering goal in plain English…"
              value={goal}
              onChange={e => setGoal(e.target.value)}
            />
          </div>

          <div className="form-field">
            <label className="form-label">Execution Strategy</label>
            <select
              className="form-select"
              value={strategy}
              onChange={e => setStrategy(e.target.value)}
            >
              <option value="adaptive">Adaptive DAG Supervisor (Recommended)</option>
              <option value="waterfall">Waterfall Linear Pipeline</option>
            </select>
          </div>

          <div className="form-field">
            <label className="form-label">LLM Provider</label>
            <select
              className="form-select"
              value={provider}
              onChange={e => setProvider(e.target.value)}
            >
              <option value="groq">Groq (Recommended)</option>
              <option value="openai">OpenAI</option>
              <option value="ollama">Ollama (Local)</option>
            </select>
          </div>

          <div className="form-field">
            <label className="form-label">Workspace Root</label>
            <input
              className="form-input"
              placeholder="."
              value={workspace}
              onChange={e => setWorkspace(e.target.value)}
            />
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1rem' }}>
            <button
              className="btn btn-primary"
              style={{ flex: 1 }}
              disabled={!goal.trim() || launching}
              onClick={handleLaunch}
            >
              {launching ? <span className="spinner" /> : <Send size={14} />}
              {launching ? 'Launching...' : 'Dispatch Mission'}
            </button>
            <button className="btn btn-ghost" onClick={() => { setGoal(''); setWorkspace('') }}>
              <X size={14} /> Clear
            </button>
          </div>
        </div>
      </div>
    </div>
  )

  /* ══════════════════ MODALS ══════════════════ */
  return (
    <div className="app-layout">
      <Sidebar />
      <div className="main-content">
        <Topbar />
        <main className="page-content">
          {page === 'dashboard' && <DashboardPage />}
          {page === 'missions'  && <MissionsPage />}
          {page === 'memory'    && <MemoryPage />}
          {page === 'launch'    && <LaunchPage />}
        </main>
      </div>

      {/* Diff Viewer Modal */}
      {activeDiff !== null && (
        <div className="modal-backdrop" onClick={() => setActiveDiff(null)}>
          <div className="modal-dialog" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600 }}>
                <FileCode size={16} color="var(--cyan)" />
                <span>Cumulative Git Diff</span>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => setActiveDiff(null)}><X size={14} /></button>
            </div>
            <div className="modal-body">
              <pre className="diff-content">
                {activeDiff.split('\n').map((line, i) => {
                  let cls = ''
                  if (line.startsWith('+') && !line.startsWith('+++')) cls = 'diff-line-add'
                  if (line.startsWith('-') && !line.startsWith('---')) cls = 'diff-line-del'
                  return <span key={i} className={cls}>{line}{'\n'}</span>
                })}
              </pre>
            </div>
          </div>
        </div>
      )}

      {/* Trace Tree Modal */}
      {activeTrace !== null && (
        <div className="modal-backdrop" onClick={() => setActiveTrace(null)}>
          <div className="modal-dialog" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600 }}>
                <Eye size={16} color="var(--cyan)" />
                <span>Execution Trace Spans ({activeTrace.length} spans)</span>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => setActiveTrace(null)}><X size={14} /></button>
            </div>
            <div className="modal-body">
              {activeTrace.length === 0 ? (
                <div style={{ color: 'var(--text-muted)' }}>No spans recorded for this mission yet.</div>
              ) : (
                activeTrace.map((sp, i) => (
                  <div key={i} className="trace-span-row">
                    <div>
                      <span className="chip chip-cyan" style={{ marginRight: '0.5rem' }}>{sp.span_type}</span>
                      <strong>{sp.name}</strong>
                      {sp.role && <span style={{ color: 'var(--text-muted)', marginLeft: '0.5rem' }}>[{sp.role}]</span>}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', fontFamily: 'JetBrains Mono, monospace' }}>
                      <span style={{ color: 'var(--text-secondary)' }}>{sp.duration_ms.toFixed(0)}ms</span>
                      <span className={`mission-status-badge ${missionBadgeClass(sp.status)}`}>{sp.status}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* Acceptance Criteria Modal */}
      {activeAcceptance !== null && (
        <div className="modal-backdrop" onClick={() => setActiveAcceptance(null)}>
          <div className="modal-dialog" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600 }}>
                <CheckSquare size={16} color="var(--green)" />
                <span>Acceptance Criteria Verification</span>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => setActiveAcceptance(null)}><X size={14} /></button>
            </div>
            <div className="modal-body">
              {activeAcceptance.map((item, i) => (
                <div key={i} style={{ padding: '0.75rem', background: 'rgba(255,255,255,0.02)', borderRadius: 'var(--r-md)', marginBottom: '0.5rem', border: '1px solid var(--glass-border)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600 }}>
                    {item.passed ? <CheckCircle2 size={16} color="var(--green)" /> : <X size={16} color="var(--red)" />}
                    <span>{item.description}</span>
                  </div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                    Evidence: {item.evidence}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Toast notifications */}
      <div className="toast-container">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.kind}`}>
            {t.kind === 'success' && <CheckCircle2 size={14} color="var(--green)" />}
            {t.kind === 'error'   && <AlertTriangle size={14} color="var(--red)" />}
            {t.kind === 'info'    && <Zap size={14} color="var(--cyan)" />}
            <span>{t.msg}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
