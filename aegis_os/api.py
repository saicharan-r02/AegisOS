"""Mission Control backend: REAL mission execution, live events, honest statistics.

Design rules that fix the old stub server:
  * ``POST /api/missions`` really runs the orchestrator in a background worker thread.
  * Events published from worker threads are marshalled safely onto the asyncio loop.
  * Pause / Resume / Cancel are honoured by the state machine before every step.
  * Every number reported by the API comes from the checkpoint database.
  * Missions killed by a server restart are marked FAILED instead of RUNNING forever.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
import time
import uuid
import zipfile
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from aegis_os.api_models import (
    AcceptanceCriteriaResponse,
    AcceptanceItem,
    ApprovalActionRequest,
    ApprovalItem,
    MissionControlActionResponse,
    MissionDiffResponse,
    MissionLaunchRequest,
    MissionListResponse,
    MissionResponse,
    MissionStatsResponse,
    MissionStepsResponse,
    PRPilotAnalyzeRequest,
    PRPilotAnalyzeResponse,
    PRPilotExecuteRequest,
    PRPilotExecuteResponse,
)
from aegis_os.integrations.github import GitHubIntegration, GitHubIssue
from aegis_os.kernel.checkpoint import CheckpointStore
from aegis_os.kernel.context import redact_sensitive_text
from aegis_os.kernel.events import EventBus, KernelEvent, PROpenedEvent
from aegis_os.kernel.state import AgentState, MissionStatus, StepStatus
from aegis_os.kernel.state_machine import MissionOrchestrator, StateMachine
from aegis_os.memory.recorder import record_mission_episode
from aegis_os.memory.store import MemoryStore
from aegis_os.pr_pilot import analyze_pr_issue, execute_pr_pilot
from aegis_os.tracing.tracer import MissionTracer
from aegis_os.verification.workspace_audit import (
    changed_files,
    collect_diff,
    ensure_git_workspace,
)
from aegis_os.workspace import repo_manager

logger = logging.getLogger("aegis.api")


class _SuppressShutdownErrors(logging.Filter):
    _PATTERNS = ("CancelledError", "lifespan", "Traceback")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(p in msg for p in self._PATTERNS)


class _SuppressWindowsResetNoise(logging.Filter):
    """Windows/Proactor prints a scary but harmless traceback when a browser tab closes."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info and isinstance(record.exc_info[1], ConnectionResetError):
            return False
        return "_ProactorBasePipeTransport._call_connection_lost" not in record.getMessage()


logging.getLogger("uvicorn.error").addFilter(_SuppressShutdownErrors())
logging.getLogger("asyncio").addFilter(_SuppressWindowsResetNoise())

global_store: CheckpointStore | None = None
global_bus: EventBus | None = None
_db_path: Path | None = None
_loop: asyncio.AbstractEventLoop | None = None

_event_lock = threading.Lock()
_clients: set[asyncio.Queue[dict[str, Any]]] = set()
_EVENT_BUFFER_MAX = 500
_event_buffer: deque[dict[str, Any]] = deque(maxlen=_EVENT_BUFFER_MAX)
_event_counter: int = 0

_mission_controls: dict[str, dict[str, Any]] = {}
_executor = ThreadPoolExecutor(
    max_workers=max(1, int(os.getenv("AEGIS_MAX_CONCURRENT_MISSIONS", "2"))),
    thread_name_prefix="aegis-mission",
)

_pending_approvals: dict[str, ApprovalItem] = {}

_rate_limits: dict[str, list[float]] = {}
_RATE_LIMIT_WINDOW = 60.0
_RATE_LIMIT_MAX_REQUESTS = 600
_STALE_MISSION_SECONDS = 900
def _publish_event(event_dict: dict[str, Any]) -> None:
    """Buffer an event and fan it out to WebSocket clients. Safe to call from ANY thread."""
    global _event_counter
    with _event_lock:
        _event_counter += 1
        event_dict["event_id"] = _event_counter
        _event_buffer.append(event_dict)
        clients = list(_clients)
    loop = _loop
    if loop is None or loop.is_closed():
        return
    for queue in clients:
        try:
            loop.call_soon_threadsafe(_safe_put, queue, event_dict)
        except RuntimeError:
            pass

def _safe_put(queue: asyncio.Queue[dict[str, Any]], item: dict[str, Any]) -> None:
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        pass

# Streamed LLM tokens arrive by the thousand; they drowned the useful events and the feed.
_NOISY_EVENTS = frozenset({"LLMTokenEvent"})


def _on_kernel_event(event: KernelEvent) -> None:
    if event.__class__.__name__ in _NOISY_EVENTS:
        return
    _publish_event(
        {
            "event_type": event.__class__.__name__,
            "payload": event.model_dump(mode="json"),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _loop
    _loop=asyncio.get_running_loop()
    yield
    _loop=None
    for ctrl in _mission_controls.values():
        if ctrl.get("status") in {"RUNNING","PAUSED"}:
            ctrl["status"] = "CANCELLED"
    if global_store:
        global_store.close()


app = FastAPI(
    title="AegisOS Mission Control API",
    description="Observable, hardened REST & WebSocket interface for AegisOS autonomous agent organization",
    version="2.1.1",
    lifespan=lifespan
)

_allowed_origins=os.getenv(
    "AEGIS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000,http://127.0.0.1:8000,http://localhost:8000",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins if "*" not in _allowed_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.middleware("http")
async def security_and_rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    if path in {"/docs", "/openapi.json", "/redoc", "/api/events"} or not path.startswith("/api/"):
        return await call_next(request)

    client_ip = request.client.host if request.client else "127.0.0.1"
    now = time.time()
    history = _rate_limits.setdefault(client_ip, [])
    _rate_limits[client_ip] = [t for t in history if now - t < _RATE_LIMIT_WINDOW]
    if len(_rate_limits[client_ip]) >= _RATE_LIMIT_MAX_REQUESTS:
        return JSONResponse(
            status_code=429, content={"detail": "Rate limit exceeded. Try again in 60s."}
        )
    _rate_limits[client_ip].append(now)

    configured_token = os.getenv("AEGIS_API_TOKEN")
    if configured_token:
        provided_token = request.headers.get("X-Aegis-Token") or request.query_params.get("token")
        if not provided_token or provided_token != configured_token:
            return JSONResponse(
                status_code=401, content={"detail": "Invalid or missing X-Aegis-Token header"}
            )

    return await call_next(request)

def reap_interrupted_missions(
    store: CheckpointStore, older_than_seconds: float = _STALE_MISSION_SECONDS
) -> int:
    """Mark missions whose process died as FAILED instead of leaving them RUNNING forever.

    Only missions that have not checkpointed for ``older_than_seconds`` are touched, so a mission
    that is genuinely running in another process (``aegis run``) is never disturbed.
    """
    reaped = 0
    now = datetime.now(UTC)
    for row in store.list_missions():
        if row.get("status") not in {"RUNNING", "PENDING"}:
            continue
        session_id = str(row["session_id"])
        if session_id in _mission_controls:
            continue
        try:
            updated = datetime.fromisoformat(str(row["updated_at"]))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
            if (now - updated).total_seconds() < older_than_seconds:
                continue
            state = store.load_latest_state(session_id)
            if state is None or state.is_terminal:
                continue
            machine = StateMachine(state=state, checkpoint_store=store)
            last = state.get_last_step()
            if last is not None and last.status == StepStatus.RUNNING:
                machine.end_step(error="Interrupted: the process stopped before this step finished.")
            machine.fail_mission(
                "Interrupted: the process running this mission stopped before it finished."
            )
            reaped += 1
        except Exception:
            logger.exception("Could not reap stale mission %s", session_id)
    return reaped

def init_app(db_path: Path) -> None:
    global global_store, global_bus, _db_path
    _db_path = Path(db_path)
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    global_store = CheckpointStore(_db_path)
    global_bus = EventBus()
    global_bus.subscribe("*", _on_kernel_event)
    try:
        count = reap_interrupted_missions(global_store)
        if count:
            logger.warning("Marked %d interrupted mission(s) as FAILED.", count)
    except Exception:
        logger.exception("Stale-mission cleanup failed")

def resolve_workspace(raw: str | None, session_id: str | None = None) -> Path:
    """Where the agents may work.

    Blank or "." means a fresh, isolated folder ``workspaces/<mission-id>``, never AegisOS's own
    source and never a folder shared with an earlier mission. An explicit path (an existing project)
    is used as given.
    """
    isolated = Path.cwd() / "workspaces" / (session_id or "default")
    value = (raw or "").strip()
    if (
        value in {"", "."}
        or any(value.lower().startswith(p) for p in ("http://", "https://", "git@", "ssh://"))
        or "github.com" in value.lower()
        or "gitlab.com" in value.lower()
    ):
        return isolated.resolve()
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    package_dir = Path(__file__).resolve().parent
    if path in {package_dir, package_dir.parent}:
        return isolated.resolve()
    return path

def _build_orchestrator(**kwargs: Any) -> Any:
    """Factory kept separate so tests can swap in a fake orchestrator."""
    return MissionOrchestrator(**kwargs)


def _control_signal(session_id: str) -> Callable[[], str]:
    def read() -> str:
        return str(_mission_controls.get(session_id, {}).get("status", "RUNNING"))

    return read


def _new_state(session_id: str, goal: str, req: MissionLaunchRequest) -> AgentState:
    from aegis_os.kernel.llm import load_runtime_config

    runtime = load_runtime_config()
    return AgentState(
        session_id=session_id,
        mission_goal=redact_sensitive_text(goal),
        status=MissionStatus.PENDING,
        max_steps=max(1, req.max_steps),
        max_tokens=runtime.max_tokens,
        max_cost_usd=runtime.max_cost_usd,
        max_wall_seconds=runtime.max_wall_seconds,
    )


def _maybe_open_pull_request(
    state: AgentState, workspace: Path, store: CheckpointStore
) -> str | None:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        logger.debug("No GITHUB_TOKEN configured; skipping PR creation.")
        return None

    target_repo = state.context_variables.get("target_repo") or ""
    issue_data = state.context_variables.get("github_issue")
    owner = ""
    repo = ""

    if issue_data and isinstance(issue_data, dict):
        owner = issue_data.get("owner", "")
        repo = issue_data.get("repo", "")
    elif target_repo:
        m = re.search(r"github\.com[/:]([^/]+)/([^/\.]+)", target_repo)
        if m:
            owner, repo = m.group(1), m.group(2)

    if not owner or not repo:
        return None

    branch = state.context_variables.get("working_branch")
    if not branch:
        if issue_data and isinstance(issue_data, dict) and "number" in issue_data:
            branch = f"aegis/issue-{issue_data['number']}"
        else:
            branch = f"aegis-fix-{state.session_id[:8]}"

    gh = GitHubIntegration(token=token)
    issue_obj = None
    if issue_data and isinstance(issue_data, dict):
        issue_obj = GitHubIssue(
            owner=owner,
            repo=repo,
            number=issue_data.get("number", 0),
            title=issue_data.get("title", ""),
            body=issue_data.get("body", ""),
            html_url=issue_data.get("html_url", ""),
            comments=issue_data.get("comments", []),
        )

    acceptance = state.context_variables.get("acceptance_criteria") or []
    test_summary = state.context_variables.get("test_summary") or {
        "passed": sum(1 for s in state.step_history if s.status == StepStatus.SUCCESS),
        "failed": sum(1 for s in state.step_history if s.status == StepStatus.FAILURE),
        "total": len(state.step_history),
    }
    cost_metrics = {
        "steps": state.current_step_index,
        "tokens": state.tokens_used,
        "cost_usd": state.cost_used_usd,
    }
    sec_summary = state.context_variables.get("sec_report")

    try:
        pr_url = gh.push_branch_and_open_pr(
            workspace=workspace,
            owner=owner,
            repo=repo,
            branch=branch,
            issue=issue_obj,
            goal=state.mission_goal,
            acceptance_criteria=acceptance,
            test_summary=test_summary,
            cost_metrics=cost_metrics,
            security_summary=sec_summary,
        )
        if pr_url:
            state.context_variables["pr_url"] = pr_url
            store.save_checkpoint(state)
            global_bus.publish(
                PROpenedEvent(
                    session_id=state.session_id,
                    pr_url=pr_url,
                    branch=branch,
                    owner=owner,
                    repo=repo,
                )
            )
            logger.info("Mission %s created Pull Request: %s", state.session_id, pr_url)
            return pr_url
    except Exception as exc:
        logger.warning("Failed to automatically open PR for mission %s: %s", state.session_id, exc)
    return None


def _run_mission(
    state: AgentState, goal: str, workspace: Path, req: MissionLaunchRequest
) -> None:
    """Worker-thread body. Uses its OWN database connection (SQLite connections are not shared)."""
    assert _db_path is not None
    session_id = state.session_id
    store = CheckpointStore(_db_path)
    error: str | None = None
    try:
        machine = StateMachine(state=state, checkpoint_store=store, event_bus=global_bus)
        machine.control_callback = _control_signal(session_id)
        machine._persist()  # visible in the registry immediately
        orchestrator = _build_orchestrator(
            workspace_root=workspace,
            llm_provider=req.provider,
            llm_model=req.model,
            state_machine=machine,
            checkpoint_store=store,
            event_bus=global_bus,
            max_repair_cycles=req.max_repairs,
            max_steps=max(1, req.max_steps),
            unsafe_local=req.unsafe_local,
            strategy=req.strategy,
        )
        orchestrator.execute_mission(goal)
    except Exception as exc:  # the thread must never die silently
        logger.exception("Mission %s crashed", session_id)
        error = f"{type(exc).__name__}: {exc}"
        try:
            latest = store.load_latest_state(session_id)
            if latest is not None and not latest.is_terminal:
                machine = StateMachine(state=latest, checkpoint_store=store, event_bus=global_bus)
                last_step = latest.get_last_step()
                if last_step is not None and last_step.status == StepStatus.RUNNING:
                    machine.end_step(error=redact_sensitive_text(error)[:300])
                machine.fail_mission(redact_sensitive_text(error)[:500])
        except Exception:
            logger.exception("Could not record failure for mission %s", session_id)
    finally:
        try:
            final = store.load_latest_state(session_id)
            if final is not None:
                record_mission_episode(final, memory_root=Path.cwd(), error=error)
                if final.status == MissionStatus.COMPLETED and not error:
                    _maybe_open_pull_request(final, workspace, store)
        except Exception:
            logger.exception("Could not record memory / PR for mission %s", session_id)
        store.close()
        ctrl = _mission_controls.get(session_id)
        if ctrl is not None:
            ctrl["status"] = "FINISHED"


# ----------------------------------------------------------------------------- REST
@app.get("/api/missions", response_model=MissionListResponse)
def get_missions():
    if not global_store:
        raise HTTPException(status_code=500, detail="Store not initialized")
    response = []
    for m in global_store.list_missions():
        response.append(
            MissionResponse(
                session_id=str(m.get("session_id")),
                goal=m.get("goal") or "Unknown Goal",
                status=m.get("status"),
                current_step_index=int(m.get("current_step_index", 0)),
                updated_at=str(m.get("updated_at", "")),
                tokens_used=int(m.get("tokens_used") or 0),
                max_tokens=int(m.get("max_tokens") or 0),
                workspace=m.get("workspace"),
                repo_url=m.get("repo_url"),
                strategy=m.get("strategy"),
                provider=m.get("provider"),
                pr_url=m.get("pr_url"),
                issue_url=m.get("issue_url"),
                failure_reason=(
                    (global_store.load_latest_state(str(m.get("session_id"))).context_variables.get("failure_reason") or None)
                    if str(m.get("status")) == "FAILED" and global_store.load_latest_state(str(m.get("session_id")))
                    else None
                ),
            )
        )
    return MissionListResponse(missions=response)  # newest first


@app.get("/api/stats", response_model=MissionStatsResponse)
def get_stats():
    if not global_store:
        raise HTTPException(status_code=500, detail="Store not initialized")
    return MissionStatsResponse(**global_store.get_stats())


@app.post("/api/missions", response_model=MissionControlActionResponse)
async def launch_mission(req: MissionLaunchRequest):
    """Start a REAL mission in a background worker thread."""
    if not global_store or _db_path is None:
        raise HTTPException(status_code=500, detail="Store not initialized")
    goal = req.goal.strip()
    session_id = str(uuid.uuid4())

    # Detect if user passed a GitHub Issue URL
    target_issue_url = (req.issue_url or "").strip()
    target_repo = (req.repo_url or "").strip()
    raw_ws = (req.workspace or "").strip()

    for candidate in [target_issue_url, target_repo, raw_ws, goal]:
        candidate_clean = (candidate or "").strip()
        if re.search(r"github\.com/[^/]+/[^/]+/issues/\d+", candidate_clean):
            target_issue_url = candidate_clean
            break

    working_branch = None
    issue_data = None
    if target_issue_url:
        gh = GitHubIntegration()
        parsed = gh.parse_issue_url(target_issue_url)
        if parsed:
            owner, repo_name, issue_num = parsed
            target_repo = f"https://github.com/{owner}/{repo_name}.git"
            working_branch = f"aegis/issue-{issue_num}"
            try:
                issue_obj = await asyncio.to_thread(gh.fetch_issue, target_issue_url)
                issue_data = {
                    "owner": issue_obj.owner,
                    "repo": issue_obj.repo,
                    "number": issue_obj.number,
                    "title": issue_obj.title,
                    "body": issue_obj.body,
                    "html_url": issue_obj.html_url,
                    "comments": issue_obj.comments,
                }
                if not goal or goal.strip() == target_issue_url:
                    goal = f"Resolve GitHub Issue #{issue_num}: {issue_obj.title}\n\nDescription:\n{issue_obj.body}"
            except Exception as exc:
                logger.warning("Could not fetch issue info for %s: %s", target_issue_url, exc)
                if not goal or goal.strip() == target_issue_url:
                    goal = f"Resolve GitHub issue #{issue_num} in {owner}/{repo_name}"

    if not goal:
        raise HTTPException(status_code=422, detail="Mission goal must not be empty.")
    if len(goal) > 4000:
        raise HTTPException(status_code=422, detail="Mission goal is too long (max 4000 characters).")

    # Detect if user passed a repo URL either in repo_url or in workspace field
    if not target_repo and (
        any(raw_ws.lower().startswith(p) for p in ("http://", "https://", "git@", "ssh://"))
        or "github.com" in raw_ws.lower()
        or "gitlab.com" in raw_ws.lower()
        or raw_ws.endswith(".git")
    ):
        target_repo = raw_ws

    if target_repo:
        try:
            workspace = await asyncio.to_thread(
                repo_manager.prepare_workspace,
                session_id,
                target_repo,
                req.repo_branch,
                working_branch,
            )
            ok, note = True, f"cloned {target_repo}"
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to clone repository '{target_repo}': {exc}",
            )
    else:
        workspace = resolve_workspace(req.workspace, session_id)
        ok, note = await asyncio.to_thread(ensure_git_workspace, workspace)
        if not ok:
            raise HTTPException(
                status_code=400,
                detail=f"Workspace '{workspace}' is not usable: {note}. Is git installed?",
            )

    state = await asyncio.to_thread(_new_state, session_id, goal, req)
    state.context_variables["workspace_root"] = str(workspace)
    if target_repo:
        state.context_variables["target_repo"] = target_repo
    if target_issue_url:
        state.context_variables["issue_url"] = target_issue_url
    if issue_data:
        state.context_variables["github_issue"] = issue_data
    if working_branch:
        state.context_variables["working_branch"] = working_branch

    await asyncio.to_thread(global_store.save_checkpoint, state)  # visible in the registry NOW
    _mission_controls[session_id] = {
        "status": "RUNNING",
        "workspace": str(workspace),
        "goal": goal,
        "state": state,
    }
    _mission_controls[session_id]["future"] = _executor.submit(
        _run_mission, state, goal, workspace, req
    )
    return MissionControlActionResponse(
        session_id=session_id,
        action="launch",
        success=True,
        message=f"Mission started in {workspace} ({note}).",
    )


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")
_ZIP_SKIP_DIRS = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", ".aegis", ".pytest_cache", "archives"}
)


def _locate_mission_workspace(session_id: str) -> Path | None:
    """Isolated folder first (workspaces/<id>); otherwise the folder recorded for the mission."""
    for base in (Path(repo_manager.BASE_WORKSPACES_DIR), Path.cwd() / "workspaces"):
        isolated = base / session_id
        if isolated.is_dir():
            return isolated
    state = global_store.load_latest_state(session_id) if global_store else None
    recorded = (state.context_variables.get("workspace_root") if state else None) or None
    if recorded:
        candidate = Path(str(recorded))
        package_root = Path(__file__).resolve().parent.parent
        if candidate.is_dir() and candidate.resolve() != package_root:
            return candidate
    return None


def _zip_workspace(workspace: Path, session_id: str) -> Path:
    holder = workspace.parent if workspace.parent.name == "workspaces" else Path.cwd() / ".aegis"
    archives = holder / "archives"
    archives.mkdir(parents=True, exist_ok=True)
    zip_path = archives / f"aegis_solved_{session_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for root, dirs, files in os.walk(workspace):
            dirs[:] = [d for d in dirs if d not in _ZIP_SKIP_DIRS]
            for name in files:
                if name.startswith(".env") or name.endswith((".pem", ".key", ".pyc")):
                    continue  # never ship secrets or build junk
                file_path = Path(root) / name
                archive.write(file_path, file_path.relative_to(workspace))
    return zip_path


@app.get("/api/missions/{session_id}/download")
def download_mission_workspace(session_id: str):
    """Download the project the agents built as a ZIP (no .git, no secrets, no caches)."""
    if not _SAFE_ID.match(session_id):
        raise HTTPException(status_code=400, detail="Invalid mission id.")
    workspace = _locate_mission_workspace(session_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="No workspace found for this mission.")
    zip_path = _zip_workspace(workspace, session_id)
    return FileResponse(
        zip_path, media_type="application/zip", filename=f"aegis_{session_id[:8]}_project.zip"
    )


@app.get("/api/missions/{session_id}/steps", response_model=MissionStepsResponse)
def get_mission_steps(session_id: str):
    if not global_store:
        raise HTTPException(status_code=500, detail="Store not initialized")
    steps = global_store.list_steps(session_id)
    if not steps:
        raise HTTPException(status_code=404, detail="Mission not found")
    return MissionStepsResponse(session_id=session_id, steps=steps)


@app.get("/api/missions/{session_id}/trace")
def get_mission_trace(session_id: str):
    """Retrieve structured span execution trace for a mission."""
    trace_db = Path(".aegis/traces.db")
    tracer = MissionTracer(mission_id=session_id, db_path=trace_db)
    try:
        trace = tracer.get_trace()
        return trace.model_dump(mode="json")
    finally:
        tracer.close()


@app.get("/api/missions/{session_id}/diff", response_model=MissionDiffResponse)
def get_mission_diff(session_id: str):
    """The mission's own changes: everything that differs from the commit it started from."""
    state = global_store.load_latest_state(session_id) if global_store else None
    if state is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    workspace = state.context_variables.get("workspace_root")
    base = state.context_variables.get("base_commit")
    if not workspace or not base:
        return MissionDiffResponse(
            session_id=session_id,
            diff="No diff recorded: this mission has no workspace/base commit on record.",
            files_changed=[],
        )
    root = Path(str(workspace))
    if not root.is_dir():
        return MissionDiffResponse(
            session_id=session_id, diff=f"Workspace no longer exists: {root}", files_changed=[]
        )
    return MissionDiffResponse(
        session_id=session_id,
        diff=collect_diff(root, str(base), max_chars=200_000) or "No changes since mission start.",
        files_changed=changed_files(root, str(base)),
    )


@app.get("/api/missions/{session_id}/acceptance", response_model=AcceptanceCriteriaResponse)
def get_mission_acceptance(session_id: str):
    """Evidence-based checklist. Never reports a pass that was not actually verified."""
    state = global_store.load_latest_state(session_id) if global_store else None
    if state is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    cv = state.context_variables
    completed = state.status == MissionStatus.COMPLETED
    items: list[AcceptanceItem] = []

    plan = cv.get("mission_plan") if isinstance(cv.get("mission_plan"), dict) else {}
    for task in (plan or {}).get("tasks", []):
        if not isinstance(task, dict):
            continue
        for number, criterion in enumerate(task.get("acceptance_criteria", []) or [], start=1):
            items.append(
                AcceptanceItem(
                    id=f"{task.get('task_id', 'T')}-crit-{number}",
                    description=str(criterion),
                    passed=completed,
                    evidence=(
                        "Mission completed and all hard invariants passed."
                        if completed
                        else f"Not verified: mission status is {state.status.value}."
                    ),
                )
            )
    for inv in cv.get("invariants", []) or []:
        if isinstance(inv, dict):
            items.append(
                AcceptanceItem(
                    id=str(inv.get("name", "invariant")),
                    description=str(inv.get("name", "invariant")).replace("_", " ").title(),
                    passed=bool(inv.get("passed")),
                    evidence=str(inv.get("details", ""))[:300],
                )
            )
    qa = cv.get("qa_report")
    if isinstance(qa, dict):
        passed_n, failed_n = int(qa.get("passed", 0)), int(qa.get("failed", 0)) + int(qa.get("errors", 0))
        items.append(
            AcceptanceItem(
                id="qa-tests",
                description="Automated tests pass",
                passed=passed_n > 0 and failed_n == 0,
                evidence=f"{passed_n} passed, {failed_n} failed/errored.",
            )
        )
    if not items:
        items.append(
            AcceptanceItem(
                id="no-evidence",
                description="No verification evidence recorded",
                passed=False,
                evidence=f"Mission status: {state.status.value}.",
            )
        )
    return AcceptanceCriteriaResponse(session_id=session_id, criteria=items)


def _control(session_id: str, action: str, new_status: str, done: str) -> MissionControlActionResponse:
    ctrl = _mission_controls.get(session_id)
    if ctrl is None or ctrl.get("status") == "FINISHED":
        return MissionControlActionResponse(
            session_id=session_id,
            action=action,
            success=False,
            message=(
                "This mission is not running in this server (it finished, was started from the "
                "CLI, or the server was restarted), so it cannot be controlled from here."
            ),
        )
    ctrl["status"] = new_status
    return MissionControlActionResponse(
        session_id=session_id, action=action, success=True, message=done
    )


def _resume_budget_block_reason(state: AgentState) -> str | None:
    """Return why a mission cannot resume without changing its original hard limits."""
    if state.current_step_index >= state.max_steps:
        return f"Step budget exhausted ({state.current_step_index}/{state.max_steps} steps)."
    # Reserve one token so a mission exactly at its ceiling is also considered exhausted.
    return state.budget_limit_reason(completion_reserve=1)


def _resume_persisted_mission(
    session_id: str, state: AgentState
) -> MissionControlActionResponse:
    """Resume execution of a persisted/paused mission without silently enlarging budgets."""
    from aegis_os.kernel.llm import load_runtime_config

    runtime = load_runtime_config()
    # Older checkpoints may already contain inflated limits from the former Resume handler.
    # Clamp them to the currently configured hard ceiling before considering a resume.
    state.max_tokens = min(state.max_tokens, runtime.max_tokens)
    if runtime.max_cost_usd is not None:
        state.max_cost_usd = (
            runtime.max_cost_usd if state.max_cost_usd is None
            else min(state.max_cost_usd, runtime.max_cost_usd)
        )
    if runtime.max_wall_seconds is not None:
        state.max_wall_seconds = (
            runtime.max_wall_seconds if state.max_wall_seconds is None
            else min(state.max_wall_seconds, runtime.max_wall_seconds)
        )

    budget_reason = _resume_budget_block_reason(state)
    if budget_reason:
        return MissionControlActionResponse(
            session_id=session_id,
            action="resume",
            success=False,
            message=(
                f"Cannot resume: {budget_reason} Mission budgets are immutable on resume. "
                "Launch a new mission with an explicitly chosen budget, or lower the scope."
            ),
        )

    ctrl = _mission_controls.get(session_id)
    if ctrl is not None and ctrl.get("status") == "RUNNING":
        return MissionControlActionResponse(
            session_id=session_id,
            action="resume",
            success=True,
            message="Mission is already running.",
        )

    ws_str = state.context_variables.get("workspace_root")
    if ws_str and Path(ws_str).is_dir():
        workspace = Path(ws_str).resolve()
    else:
        workspace = resolve_workspace(".", session_id)

    ensure_git_workspace(workspace)

    state.status = MissionStatus.PAUSED
    state.consecutive_failures = 0
    state.context_variables.pop("failure_reason", None)
    state.context_variables.pop("partial_result_reason", None)
    state.context_variables.pop("approval_required_for_step", None)
    # A resume continues under the original hard budget. Never add hidden token/step headroom.

    if global_store:
        global_store.save_checkpoint(state)

    req = MissionLaunchRequest(
        goal=state.mission_goal,
        workspace=str(workspace),
        max_steps=state.max_steps,
    )

    _mission_controls[session_id] = {
        "status": "RUNNING",
        "workspace": str(workspace),
        "goal": state.mission_goal,
        "state": state,
    }
    _mission_controls[session_id]["future"] = _executor.submit(
        _run_mission, state, state.mission_goal, workspace, req
    )

    return MissionControlActionResponse(
        session_id=session_id,
        action="resume",
        success=True,
        message=f"Mission {session_id[:8]} resumed from checkpoint.",
    )


@app.post("/api/missions/{session_id}/pause", response_model=MissionControlActionResponse)
def pause_mission(session_id: str):
    return _control(session_id, "pause", "PAUSED", "Pause requested: the mission stops before its next step.")


@app.post("/api/missions/{session_id}/resume", response_model=MissionControlActionResponse)
def resume_mission(session_id: str):
    ctrl = _mission_controls.get(session_id)
    fut = ctrl.get("future") if ctrl else None
    if ctrl is not None and ctrl.get("status") == "PAUSED" and fut is not None and not fut.done():
        in_mem_state = ctrl.get("state")
        if in_mem_state is not None:
            budget_reason = _resume_budget_block_reason(in_mem_state)
            if budget_reason:
                return MissionControlActionResponse(
                    session_id=session_id,
                    action="resume",
                    success=False,
                    message=(
                        f"Cannot resume: {budget_reason} Mission budgets are immutable on resume. "
                        "Launch a new mission with an explicitly chosen budget, or lower the scope."
                    ),
                )
            in_mem_state.consecutive_failures = 0
            in_mem_state.context_variables.pop("partial_result_reason", None)
            in_mem_state.context_variables.pop("failure_reason", None)
        ctrl["status"] = "RUNNING"
        return MissionControlActionResponse(
            session_id=session_id, action="resume", success=True, message="Mission resumed."
        )

    if global_store is not None:
        state = global_store.load_latest_state(session_id)
        if state is not None:
            return _resume_persisted_mission(session_id, state)

    return MissionControlActionResponse(
        session_id=session_id,
        action="resume",
        success=False,
        message=(
            "This mission is not running in this server (it finished, was started from the "
            "CLI, or the server was restarted), so it cannot be controlled from here."
        ),
    )


@app.post("/api/missions/{session_id}/cancel", response_model=MissionControlActionResponse)
def cancel_mission(session_id: str):
    return _control(
        session_id, "cancel", "CANCELLED", "Cancel requested: the mission stops before its next step."
    )


@app.get("/api/approvals", response_model=list[ApprovalItem])
def list_approvals():
    """List pending risky commands awaiting human sign-off."""
    return [item for item in _pending_approvals.values() if item.status == "PENDING"]


@app.post("/api/approvals/{approval_id}/action")
def act_on_approval(approval_id: str, req: ApprovalActionRequest):
    item = _pending_approvals.get(approval_id)
    if not item:
        raise HTTPException(status_code=404, detail="Approval request not found")
    action = req.action.lower()
    if action not in {"approve", "deny"}:
        raise HTTPException(status_code=400, detail="Action must be 'approve' or 'deny'")
    item.status = "APPROVED" if action == "approve" else "DENIED"
    return {"approval_id": approval_id, "status": item.status}


@app.get("/api/memory")
def get_memory_records():
    """Return stored episodic memories and learned conventions."""
    mem_store = MemoryStore(workspace_root=Path.cwd())
    return {
        "episodes": [e.model_dump(mode="json") for e in mem_store.get_all_episodes()],
        "conventions": [c.model_dump(mode="json") for c in mem_store.get_all_conventions()],
    }


@app.websocket("/api/events")
async def websocket_events(websocket: WebSocket, last_event_id: int | None = Query(default=None)):
    """Live event stream. One shared buffer, one queue per client, no leaked subscribers."""
    await websocket.accept()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=2000)
    with _event_lock:
        replay = (
            [e for e in _event_buffer if e.get("event_id", 0) > last_event_id]
            if last_event_id is not None
            else []
        )
        _clients.add(queue)
    try:
        for buffered in replay:
            await websocket.send_json(buffered)
        while True:
            await websocket.send_json(await queue.get())
    except (WebSocketDisconnect, asyncio.CancelledError, RuntimeError):
        pass
    finally:
        with _event_lock:
            _clients.discard(queue)


@app.post("/api/events/ingest")
async def ingest_event(event_data: dict):
    """Receive events from a separate CLI process (`aegis run`) and broadcast them."""
    event_data.setdefault("timestamp", datetime.now(UTC).isoformat())
    _publish_event(event_data)
    return {"ok": True, "clients": len(_clients)}


@app.post("/api/pr-pilot/analyze", response_model=PRPilotAnalyzeResponse)
async def pr_pilot_analyze(req: PRPilotAnalyzeRequest):
    """Run PR Pilot issue analysis, patch synthesis, and 10-step PR guide generation."""
    try:
        result = await asyncio.to_thread(
            analyze_pr_issue,
            issue_url=req.issue_url,
            github_username=req.github_username,
            issue_text=req.issue_text,
            provider=req.provider,
            model=req.model,
        )
        return PRPilotAnalyzeResponse(**result.to_dict())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@app.post("/api/pr-pilot/execute", response_model=PRPilotExecuteResponse)
async def pr_pilot_execute(req: PRPilotExecuteRequest) -> PRPilotExecuteResponse:
    try:
        result = await asyncio.to_thread(
            execute_pr_pilot,
            issue_url=req.issue_url,
            github_username=req.github_username,
            branch=req.branch,
            commit_message=req.commit_message,
            pr_title=req.pr_title,
            pr_body=req.pr_body,
            patch=req.patch,
            tests=req.tests,
            summary=req.summary,
            root_cause=req.root_cause,
            affected_files=req.affected_files,
        )
        return PRPilotExecuteResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

# Build output of the React + Vite app in web/ (`npm run build` writes here).
_STATIC_DIR = Path(os.path.dirname(__file__)) / "static"


@app.get("/pr-pilot")
def serve_pr_pilot():
    """Serve the PR Pilot single-page app built from web/."""
    index_file = _STATIC_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(
            status_code=503,
            detail="PR Pilot UI is not built. Run `npm install && npm run build` inside web/.",
        )
    return FileResponse(index_file, media_type="text/html")


@app.get("/", include_in_schema=False)
def serve_root() -> RedirectResponse:
    """PR Pilot is the only web interface, so the root URL lands on it."""
    return RedirectResponse(url="/pr-pilot")


# Hashed JS/CSS bundles referenced by index.html. check_dir=False keeps the API
# importable (and testable) before the UI has been built.
app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets", check_dir=False), name="ui-assets")
