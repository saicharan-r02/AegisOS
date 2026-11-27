import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Shield, Terminal, CheckCircle2, Zap, LayoutDashboard,
  ListOrdered, Rocket, AlertTriangle, RefreshCw,
  X, Send, Database, Cpu, Pause, Play,
  Square, Eye, CheckSquare, BookOpen, FileCode, Check, Ban, Download, RotateCcw
} from 'lucide-react'
import './index.css'

interface KernelEvent { event_type: string; payload: any; event_id?: number }
interface Mission {
  session_id: string; goal: string; status: string;
  current_step_index: number; updated_at: string;
  tokens_used?: number; max_tokens?: number;
  workspace?: string; repo_url?: string; strategy?: string; provider?: string;
  pr_url?: string; issue_url?: string;
}
interface Stats {
  total: number; completed: number; failed: number; aborted: number;
  running: number; paused: number; pending: number;
  total_steps: number; total_tokens: number; total_cost_usd: number;
  success_rate: number | null
}
const EMPTY_STATS: Stats = {
  total: 0, completed: 0, failed: 0, aborted: 0, running: 0, paused: 0, pending: 0,
  total_steps: 0, total_tokens: 0, total_cost_usd: 0, success_rate: null,
}
const TERMINAL = ['COMPLETED', 'FAILED', 'ABORTED']
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

const isDev = typeof window !== 'undefined' && (window.location.port === '5173' || window.location.port === '3000')
const API = isDev ? 'http://127.0.0.1:8000' : ''
const wsProto = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:'
const WS = isDev
  ? 'ws://127.0.0.1:8000'
  : (typeof window !== 'undefined' ? `${wsProto}//${window.location.host}` : 'ws://127.0.0.1:8000')

const AGENTS = [
  { id: 'CTO', label: 'Architect', emoji: '🧠', color: '#00d2ff', rgb: '0,210,255' },
  { id: 'DEV', label: 'Developer', emoji: '⚡', color: '#00e87a', rgb: '0,232,122' },
  { id: 'QA', label: 'QA Tester', emoji: '🔬', color: '#f5b731', rgb: '245,183,49' },
  { id: 'SEC', label: 'Security', emoji: '🛡️', color: '#d942ff', rgb: '217,66,255' },
  { id: 'OPS', label: 'DevOps', emoji: '🔧', color: '#4a7fdb', rgb: '74,127,219' },
]

function roleTag(role: string) {
  const r = (role || '').toUpperCase()
  if (r.includes('CTO')) return 'tag-cto'
  if (r.includes('DEV')) return 'tag-dev'
  if (r.includes('QA')) return 'tag-qa'
  if (r.includes('SEC')) return 'tag-sec'
  if (r.includes('OPS')) return 'tag-ops'
  if (r.includes('PR')) return 'tag-dev'
  return 'tag-sys'
}

function dotClass(evt: KernelEvent) {
  if (evt.event_type === 'StepCompletedEvent') {
    return evt.payload?.step?.status === 'SUCCESS' ? 'success' : 'error'
  }
  if (evt.event_type === 'MissionStatusChangedEvent') {
    const s = evt.payload?.new_status
    if (s === 'COMPLETED') return 'success'
    if (s === 'FAILED') return 'error'
    return 'running'
  }
  if (evt.event_type === 'PROpenedEvent' || evt.event_type === 'pr.opened') return 'success'
  if (evt.event_type === 'StepStartedEvent') return 'running'
  return 'info'
}

function evtLabel(evt: KernelEvent): string {
  switch (evt.event_type) {
    case 'PROpenedEvent':
    case 'pr.opened':
      return `🎉 Pull Request Opened: ${evt.payload?.pr_url || ''}`
    case 'StateTransitionEvent':
      return `Handoff → ${evt.payload?.to_role || '?'}`
    case 'StepStartedEvent':
      return `${evt.payload?.step?.role || ''} starting step`
    case 'StepCompletedEvent': {
      const step = evt.payload?.step
      const tool = step?.tool_name ? `${step.tool_name} ` : ''
      if (step?.status === 'SUCCESS') return `${tool}✓ ${Math.round(step?.duration_ms ?? 0)}ms`
      const why = String(step?.error ?? '').split('\n')[0].slice(0, 110)
      return `${tool}✗ ${why || 'failed'}`
    }
    case 'LLMCallStartedEvent':
      return `thinking… (${String(evt.payload?.model ?? '').split('/').pop() || 'LLM'})`
    case 'LLMCallCompletedEvent': {
      const model = String(evt.payload?.model ?? '').split('/').pop() || 'LLM'
      return `${model} · ${evt.payload?.input_tokens ?? 0} in → ${evt.payload?.output_tokens ?? 0} out`
    }
    case 'MissionStatusChangedEvent':
      return `Mission → ${evt.payload?.new_status}`
    default:
      return evt.event_type.replace(/Event$/, '')
  }
}

function evtRole(evt: KernelEvent): string {
  if (evt.event_type === 'PROpenedEvent' || evt.event_type === 'pr.opened') return 'PR'
  return (
    evt.payload?.step?.role ||
    evt.payload?.to_role ||
    evt.payload?.role ||
    (evt.event_type === 'MissionStatusChangedEvent' ? 'SYS' : '')
  )
}

function nowStr() {
  return new Date().toLocaleTimeString('en-US', { hour12: false })
}

function missionBadgeClass(status: string) {
  switch (status?.toUpperCase()) {
    case 'COMPLETED': return 'msb-completed'
    case 'RUNNING': return 'msb-running'
    case 'FAILED': return 'msb-failed'
    default: return 'msb-pending'
  }
}

export default function App() {
  const [page, setPage] = useState<Page>('dashboard')
  const [events, setEvents] = useState<(KernelEvent & { ts: string })[]>([])
  const [missions, setMissions] = useState<Mission[]>([])
  const [connected, setConnected] = useState(false)
  const [activeRole, setActiveRole] = useState<string>('')
  const [toasts, setToasts] = useState<Toast[]>([])
  const toastId = useRef(0)

  const [stats, setStats] = useState<Stats>(EMPTY_STATS)
  const pendingSelect = useRef<string | null>(null)
  const statsTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const everConnected = useRef(false)

  const [approvals, setApprovals] = useState<ApprovalItem[]>([])

  const [activeDiff, setActiveDiff] = useState<string | null>(null)
  const [activeTrace, setActiveTrace] = useState<SpanRecord[] | null>(null)
  const [activeAcceptance, setActiveAcceptance] = useState<AcceptanceItem[] | null>(null)
  const [selectedMission, setSelectedMission] = useState<Mission | null>(null)

  const [memoryData, setMemoryData] = useState<{ episodes: any[]; conventions: any[] }>({ episodes: [], conventions: [] })

  const [goal, setGoal] = useState('')
  const [repoUrl, setRepoUrl] = useState('')
  const [repoBranch, setRepoBranch] = useState('main')
  const [provider, setProvider] = useState('nvidia')
  const [workspace, setWorkspace] = useState('')
  const [strategy, setStrategy] = useState('adaptive')
  const [launching, setLaunching] = useState(false)
  const [issueUrl, setIssueUrl] = useState('')
  const [issueGoalExtra, setIssueGoalExtra] = useState('')
  const [issueLaunching, setIssueLaunching] = useState(false)

  const addToast = useCallback((msg: string, kind: Toast['kind'] = 'info') => {
    const id = ++toastId.current
    setToasts(p => [...p, { id, msg, kind }])
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 4000)
  }, [])

  const fetchStats = useCallback(() => {
    fetch(`${API}/api/stats`)
      .then(r => r.json())
      .then(d => { if (typeof d.total === 'number') setStats(d) })
      .catch(() => { })
  }, [])

  const fetchMissions = useCallback(() => {
    fetch(`${API}/api/missions`)
      .then(r => r.json())
      .then(d => {
        if (!Array.isArray(d.missions)) return
        const ms = d.missions as Mission[]
        setMissions(ms)
        setSelectedMission(prev => {
          if (pendingSelect.current) {
            const wanted = ms.find(m => m.session_id === pendingSelect.current)
            if (wanted) { pendingSelect.current = null; return wanted }
          }
          if (prev) return ms.find(m => m.session_id === prev.session_id) ?? ms[0] ?? null
          return ms.find(m => !TERMINAL.includes(m.status)) ?? ms[0] ?? null
        })
      })
      .catch(() => { })
    fetchStats()
  }, [fetchStats])

  const scheduleStatsRefresh = useCallback(() => {
    if (statsTimer.current) return
    statsTimer.current = setTimeout(() => { statsTimer.current = null; fetchStats() }, 800)
  }, [fetchStats])

  const fetchApprovals = useCallback(() => {
    fetch(`${API}/api/approvals`)
      .then(r => r.json())
      .then(d => { if (Array.isArray(d)) setApprovals(d) })
      .catch(() => { })
  }, [])

  const fetchMemory = useCallback(() => {
    fetch(`${API}/api/memory`)
      .then(r => r.json())
      .then(d => { setMemoryData(d) })
      .catch(() => { })
  }, [])

  useEffect(() => {
    fetchMissions()
    fetchApprovals()
    fetchMemory()
    const timer = setInterval(() => { fetchApprovals(); fetchMissions() }, 4000)
    return () => clearInterval(timer)
  }, [fetchMissions, fetchApprovals, fetchMemory])

  useEffect(() => {
    let ws: WebSocket
    let retryTimer: ReturnType<typeof setTimeout>

    function connect() {
      ws = new WebSocket(`${WS}/api/events`)
      ws.onopen = () => {
        setConnected(true)
        if (!everConnected.current) { everConnected.current = true; addToast('Mission Control Live', 'success') }
      }
      ws.onclose = () => { setConnected(false); retryTimer = setTimeout(connect, 3000) }
      ws.onerror = () => { setConnected(false) }
      ws.onmessage = (msg) => {
        try {
          const data: KernelEvent = JSON.parse(msg.data)
          if (data.event_type === 'LLMTokenEvent') return
          const enriched = { ...data, ts: nowStr() }
          setEvents(p => [enriched, ...p].slice(0, 80))

          const role = evtRole(data)
          if (role && data.event_type !== 'MissionStatusChangedEvent') setActiveRole(role)
          if (data.event_type === 'MissionStatusChangedEvent') {
            fetchMissions()
            fetchApprovals()
            if (TERMINAL.includes(data.payload?.new_status)) setActiveRole('')
          }
          if (data.event_type === 'PROpenedEvent' || data.event_type === 'pr.opened') {
            fetchMissions()
            addToast(`Pull Request opened on GitHub! Ready to review.`, 'success')
          }
          if (data.event_type === 'StepCompletedEvent') scheduleStatsRefresh()
        } catch { /* ignore */ }
      }
    }
    connect()
    return () => { ws?.close(); clearTimeout(retryTimer) }
  }, [addToast, fetchMissions, fetchApprovals, scheduleStatsRefresh])

  const handleLaunch = async () => {
    if (!goal.trim()) return
    setLaunching(true)
    const isUrl = workspace.startsWith('http') || workspace.startsWith('git@') || workspace.includes('github.com')
    try {
      const res = await fetch(`${API}/api/missions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal,
          repo_url: repoUrl.trim() || (isUrl ? workspace.trim() : undefined),
          repo_branch: repoBranch.trim() || 'main',
          provider,
          workspace: isUrl ? '.' : (workspace || '.'),
          strategy,
        }),
      })
      const d = await res.json()
      if (res.ok && d.success) {
        addToast(d.message || `Mission started: ${d.session_id}`, 'success')
        pendingSelect.current = d.session_id
        setGoal('')
        setRepoUrl('')
        setWorkspace('')
        setActiveRole('')
        fetchMissions()
        setTimeout(fetchMissions, 700)
        setPage('dashboard')
      } else {
        addToast(`Launch failed: ${d.detail || d.message || res.statusText}`, 'error')
      }
    } catch {
      addToast('Cannot connect to Aegis API backend', 'error')
    } finally {
      setLaunching(false)
    }
  }

  const handleIssueLaunch = async () => {
    if (!issueUrl.trim() || !issueUrl.includes('github.com')) return
    setIssueLaunching(true)
    try {
      const res = await fetch(`${API}/api/missions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal: issueGoalExtra.trim() || `Autonomous fix: ${issueUrl.trim()}`,
          issue_url: issueUrl.trim(),
          repo_url: issueUrl.trim(),
          provider,
          workspace: '.',
          strategy,
        }),
      })
      const d = await res.json()
      if (res.ok && d.success) {
        addToast(`🚀 Issue mission launched → ${d.session_id}`, 'success')
        pendingSelect.current = d.session_id
        setIssueUrl('')
        setIssueGoalExtra('')
        setActiveRole('')
        fetchMissions()
        setTimeout(fetchMissions, 700)
        setPage('dashboard')
      } else {
        addToast(`Launch failed: ${d.detail || d.message || res.statusText}`, 'error')
      }
    } catch {
      addToast('Cannot connect to Aegis API backend', 'error')
    } finally {
      setIssueLaunching(false)
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

  const reuseMission = (m: Mission) => {
    setGoal(m.goal)
    if (m.issue_url) {
      setIssueUrl(m.issue_url)
      setPage('launch')
      addToast(`Issue URL loaded — click "Solve Issue & Open PR" to re-run.`, 'info')
      return
    }
    if (m.repo_url) {
      setRepoUrl(m.repo_url)
    } else if (m.workspace && (m.workspace.startsWith('http') || m.workspace.startsWith('git@') || m.workspace.includes('github.com'))) {
      setRepoUrl(m.workspace)
      setWorkspace('')
    } else if (m.workspace && m.workspace !== '.') {
      setWorkspace(m.workspace)
    }
    if (m.strategy) setStrategy(m.strategy)
    if (m.provider) setProvider(m.provider)
    setPage('launch')
    addToast(`Mission parameters loaded into Launch Mission! Ready to dispatch.`, 'info')
  }

  const resumeMission = async (sessionId: string) => {
    try {
      const res = await fetch(`${API}/api/missions/${sessionId}/resume`, { method: 'POST' })
      const d = await res.json()
      addToast(d.message, d.success ? 'success' : 'error')
      if (d.success) {
        const found = missions.find(m => m.session_id === sessionId)
        if (found) setSelectedMission(found)
        setPage('dashboard')
      }
      fetchMissions()
    } catch {
      addToast('Failed to resume mission: backend error', 'error')
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
  const renderSidebar = () => (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-icon">
          <Shield size={20} color="var(--cyan)" />
        </div>
        <div className="brand-text">
          <span className="brand-name">AegisOS</span>
          <span className="brand-badge">v2.1.1 STABILITY</span>
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
        <a
          className="nav-item"
          href="/pr-pilot"
          style={{ textDecoration: 'none' }}
        >
          <FileCode size={16} />
          <span>PR Pilot</span>
        </a>
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
  const renderTopbar = () => (
    <header className="topbar">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem' }}>
        <span style={{ fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-primary)' }}>
          {page === 'dashboard' && 'War Room Live Operations'}
          {page === 'missions' && 'Historical Missions & Audit Traces'}
          {page === 'memory' && 'Cross-Mission Episodic Memory & Learned Conventions'}
          {page === 'launch' && 'Dispatch Autonomous Engineering Mission'}
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

  const renderDashboardPage = () => (
    <div className="dashboard-grid">
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

      <div className="stats-row" style={{ gridColumn: '1 / -1' }}>
        <div className="stat-card">
          <div className="stat-label">Total Missions</div>
          <div className="stat-val">{stats.total}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Success Rate</div>
          <div className="stat-val" style={{ color: 'var(--green)' }}>
            {stats.success_rate === null ? '—' : `${Math.round(stats.success_rate * 100)}%`}
            <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}> {stats.completed} of {stats.completed + stats.failed + stats.aborted} finished</span>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Steps Executed</div>
          <div className="stat-val">{stats.total_steps.toLocaleString()}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Tokens Used (all missions)</div>
          <div className="stat-val" style={{ color: 'var(--cyan)' }}>
            {stats.total_tokens.toLocaleString()}
            {selectedMission && selectedMission.max_tokens ? (
              <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>
                {' '}· focused: {(selectedMission.tokens_used ?? 0).toLocaleString()} / {selectedMission.max_tokens.toLocaleString()}
              </span>
            ) : null}
          </div>
        </div>
      </div>

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
            {selectedMission.status === 'PAUSED' ? (
              <button className="btn btn-primary btn-sm" style={{ background: '#10b981', color: '#fff' }} onClick={() => handleControlAction('resume')} title="Resume paused mission">
                <Play size={14} /> Resume
              </button>
            ) : (
              <button className="btn btn-ghost btn-sm" onClick={() => handleControlAction('resume')} title="Resume mission">
                <Play size={14} /> Resume
              </button>
            )}
            <button className="btn btn-ghost btn-sm" onClick={() => reuseMission(selectedMission)} title="Reuse mission parameters in Launch Mission">
              <RotateCcw size={14} /> Reuse
            </button>
            <button className="btn btn-danger btn-sm" onClick={() => handleControlAction('cancel')} title="Abort mission">
              <Square size={14} /> Cancel
            </button>
            <a className="btn btn-ghost btn-sm" href={`${API}/api/missions/${selectedMission.session_id}/download`}
              title="Download the project the agents built (ZIP)" style={{ textDecoration: 'none' }}>
              <Download size={14} /> Download
            </a>
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

      {selectedMission?.pr_url && (
        <div className="card" style={{
          gridColumn: '1 / -1',
          padding: '0.9rem 1.25rem',
          background: 'rgba(16, 185, 129, 0.12)',
          border: '1px solid rgba(16, 185, 129, 0.45)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderRadius: 8,
          boxShadow: '0 0 16px rgba(16, 185, 129, 0.15)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ fontSize: '1.4rem' }}>🛡️</span>
            <div>
              <div style={{ fontSize: '0.86rem', fontWeight: 700, color: '#34d399', letterSpacing: '0.02em' }}>
                Autonomous Pull Request Opened on GitHub
              </div>
              <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', marginTop: 2 }}>
                All 4 Hard Invariants passed (QA suite verified, Security cleared, Reviewer approved). Single human gate ready:
              </div>
            </div>
          </div>
          <a
            href={selectedMission.pr_url}
            target="_blank"
            rel="noreferrer"
            className="btn btn-primary btn-sm"
            style={{
              background: '#10b981',
              color: '#022c22',
              fontWeight: 700,
              textDecoration: 'none',
              padding: '0.5rem 1.1rem',
              fontSize: '0.8rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem'
            }}
          >
            Review & Merge PR on GitHub ↗
          </a>
        </div>
      )}

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

  const renderMissionsPage = () => (
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
                {m.status === 'PAUSED' && (
                  <button
                    className="btn btn-primary btn-sm"
                    style={{ background: '#10b981', color: '#fff' }}
                    onClick={(e) => { e.stopPropagation(); resumeMission(m.session_id) }}
                    title="Resume paused mission"
                  >
                    <Play size={12} style={{ marginRight: 3 }} /> Resume
                  </button>
                )}
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={(e) => { e.stopPropagation(); reuseMission(m) }}
                  title="Reuse mission parameters in Launch Mission"
                >
                  <RotateCcw size={12} style={{ marginRight: 3 }} /> Reuse
                </button>
                <button className="btn btn-ghost btn-sm" onClick={(e) => { e.stopPropagation(); openDiffModal(m.session_id) }}>
                  Diff
                </button>
                <button className="btn btn-ghost btn-sm" onClick={(e) => { e.stopPropagation(); openTraceModal(m.session_id) }}>
                  Trace
                </button>
                {m.pr_url && (
                  <a
                    className="btn btn-sm"
                    style={{ background: 'rgba(16, 185, 129, 0.2)', color: '#34d399', textDecoration: 'none', border: '1px solid rgba(16, 185, 129, 0.45)', padding: '0.2rem 0.6rem', fontSize: '0.72rem', fontWeight: 600 }}
                    href={m.pr_url}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    title="View open Pull Request on GitHub"
                  >
                    PR ↗
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )

  const renderMemoryPage = () => (
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

  const renderLaunchPage = () => (
    <div style={{ maxWidth: 620, display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>

      <div style={{
        background: 'linear-gradient(135deg, rgba(0,210,255,0.08) 0%, rgba(16,185,129,0.08) 100%)',
        border: '1px solid rgba(16,185,129,0.4)',
        borderRadius: 10,
        padding: '1.25rem',
        boxShadow: '0 0 24px rgba(16,185,129,0.1)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.9rem' }}>
          <span style={{ fontSize: '1.3rem' }}>🚀</span>
          <div>
            <div style={{ fontSize: '0.92rem', fontWeight: 700, color: '#34d399', letterSpacing: '0.01em' }}>
              Solve GitHub Issue &amp; Open Pull Request
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 1 }}>
              Gold Standard AI Agent Pipeline · Issue → Architect → Dev → QA+Sec → PR (Human Gate: Merge)
            </div>
          </div>
        </div>

        <div className="form-field" style={{ marginBottom: '0.75rem' }}>
          <label className="form-label" style={{ color: '#6ee7b7', fontSize: '0.76rem' }}>
            GitHub Issue URL *
          </label>
          <input
            className="form-input"
            style={{ borderColor: issueUrl.includes('github.com') ? 'rgba(16,185,129,0.6)' : undefined }}
            placeholder="https://github.com/<owner>/<repo>/issues/<number>"
            value={issueUrl}
            onChange={e => setIssueUrl(e.target.value)}
          />
          <span style={{ fontSize: '0.69rem', color: 'var(--text-muted)', marginTop: '0.2rem', display: 'block' }}>
            AegisOS fetches the issue, checks out branch <code>aegis/issue-N</code>, runs the full 4-agent pipeline (Architect → Developer → QA + Security in parallel), then opens a PR. You review and click <strong>Merge</strong> — that's the only human step.
          </span>
        </div>

        <div className="form-field" style={{ marginBottom: '0.9rem' }}>
          <label className="form-label" style={{ color: '#6ee7b7', fontSize: '0.76rem' }}>
            Extra Context (optional)
          </label>
          <textarea
            className="form-textarea"
            style={{ minHeight: 60 }}
            placeholder="Any extra guidance for the agents (e.g. 'keep backward compatibility', 'use pytest fixtures'). Leave blank to use the issue body alone."
            value={issueGoalExtra}
            onChange={e => setIssueGoalExtra(e.target.value)}
          />
        </div>

        <button
          className="btn btn-primary"
          style={{
            width: '100%',
            background: issueUrl.includes('github.com') ? 'linear-gradient(90deg,#059669,#10b981)' : undefined,
            color: '#022c22',
            fontWeight: 700,
            fontSize: '0.9rem',
            padding: '0.65rem 1rem',
            justifyContent: 'center',
            gap: '0.5rem',
            opacity: !issueUrl.trim() || issueLaunching ? 0.6 : 1,
          }}
          disabled={!issueUrl.trim() || issueLaunching || !issueUrl.includes('github.com')}
          onClick={handleIssueLaunch}
        >
          {issueLaunching ? <span className="spinner" /> : <span>🛡️</span>}
          {issueLaunching ? 'Dispatching Issue Agent Pipeline...' : 'Solve Issue & Open PR →'}
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.08)' }} />
        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          or dispatch a general mission
        </span>
        <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.08)' }} />
      </div>

      <div className="launcher-card">
        <div className="launcher-header">
          <Rocket size={15} color="var(--cyan)" />
          <span style={{ fontSize: '0.88rem', fontWeight: 600 }}>General Mission Configuration</span>
        </div>
        <div className="launcher-body">
          <div className="form-field">
            <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Download size={14} color="var(--cyan)" /> Target Repository URL (optional)
            </label>
            <input
              className="form-input"
              placeholder="https://github.com/<owner>/<repo>"
              value={repoUrl}
              onChange={e => setRepoUrl(e.target.value)}
            />
          </div>

          {repoUrl.trim() && (
            <div className="form-field">
              <label className="form-label">Target Branch</label>
              <input
                className="form-input"
                placeholder="main"
                value={repoBranch}
                onChange={e => setRepoBranch(e.target.value)}
              />
            </div>
          )}

          <div className="form-field">
            <label className="form-label">Mission Goal / Objective *</label>
            <textarea
              className="form-textarea"
              placeholder="Describe what needs to be built or fixed (e.g. Fix failing tests, add feature, refactor code)..."
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
              <option value="nvidia">NVIDIA NIM (Nemotron / MiniMax)</option>
            </select>
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
            <button className="btn btn-ghost" onClick={() => { setGoal(''); setRepoUrl(''); setWorkspace('') }}>
              <X size={14} /> Clear
            </button>
          </div>
        </div>
      </div>
    </div>
  )

  return (
    <div className="app-layout">
      {renderSidebar()}
      <div className="main-content">
        {renderTopbar()}
        <main className="page-content">
          {page === 'dashboard' && renderDashboardPage()}
          {page === 'missions' && renderMissionsPage()}
          {page === 'memory' && renderMemoryPage()}
          {page === 'launch' && renderLaunchPage()}
        </main>
      </div>

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

      <div className="toast-container">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.kind}`}>
            {t.kind === 'success' && <CheckCircle2 size={14} color="var(--green)" />}
            {t.kind === 'error' && <AlertTriangle size={14} color="var(--red)" />}
            {t.kind === 'info' && <Zap size={14} color="var(--cyan)" />}
            <span>{t.msg}</span>
          </div>
        ))}
      </div>
    </div>
  )
}