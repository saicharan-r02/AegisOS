# Architecture Decision Records (ADR) - AegisOS v2

## ADR 0001: Baseline Audit and Ground Rules for Autonomous Agent Transformation
- **Status:** Accepted
- **Date:** 2026-10-19
- **Deciders:** Staff Engineer & Agent Architect

### Context
AegisOS is being transformed from a prototype ReAct multi-agent pipeline into an enterprise-grade, truly autonomous software-engineering agent. Before refactoring the core execution loop, LLM integration, sandboxing, and codebase intelligence, a rigorous Phase 0 architectural audit and empirical benchmark baseline must be established.

### Decisions
1. **Branching Strategy:** All Phase 0-11 development occurs on branch `aegis-v2`. Each phase concludes with a green test suite, ruff/mypy validation, and an atomic commit.
2. **Backward Compatibility:** All existing CLI subcommands (`run`, `audit`, `test`, `status`, `rollback`, `benchmark`, `server`) remain functional with their existing flags, while being extended to support new capabilities (such as `--strategy`, `--mode`, `--tdd`, etc.).
3. **Execution Environment:** Windows PowerShell and Linux/macOS are both tier-1 supported environments. All path manipulation uses `pathlib.Path`. Subprocess execution uses explicit arguments and strict escaping instead of arbitrary shell invocations.
4. **Benchmark Verification:** Evals will use real tasks with hidden test fixtures (`eval/tasks/`). No mocks are permitted inside evaluation verification scripts.
5. **Security Isolation:** Code changes must not access outside paths or sensitive files (`.env`, `.git/`, `.aegis/`). Security and command policies are enforced deterministically in Python code, not via LLM prompts alone.

## ADR 0002: Provider Routing and Mission Budgets
- **Status:** Accepted
- **Date:** 2026-10-20
- **Context:** The Phase 0 live run stalled while the legacy fallback chain repeatedly retried unavailable models, and the agent loop had no request timeout, cost accounting, or bounded prompt context.
- **Decision:** Keep the legacy `get_llm()` return type for non-role callers. Role-based agents use a provider-neutral router configured from `aegis.toml`; it supports ordered fallback, bounded retries, cooldown circuits, native tool calls, usage accounting, and token/cost/time budgets. OpenAI-compatible providers use the OpenAI chat adapter with a configured base URL. Anthropic and Gemini use their LangChain adapters.
- **Dependencies:** `langchain-anthropic` adds the Anthropic adapter; `langchain-google-genai` adds the Gemini adapter. Existing OpenAI and Groq adapters remain in use.
- **Prompt caching:** OpenAI caching is provider-managed and enabled by its API when eligible; other adapters advertise caching as unsupported until their cache controls are configured and tested.
- **Trade-off:** Provider IDs, model IDs, timeouts, prices, budgets, and role context limits stay in configuration. Models without a price entry cannot be used while a dollar budget is enabled.

*Status note: superseded in v2.1: `SUPPORTED_PROVIDERS = ("nvidia",)`; the other adapters are no longer wired.*

## ADR 0003: Deterministic Sandbox Isolation and In-Code Security Policy
- **Status:** Accepted
- **Date:** 2026-10-20
- **Context:** The Phase 0 audit revealed that commands ran directly on the host shell without command categorization, PathGuard allowed access to internal `.env` and `.git` files, and security audits relied solely on LLM prompt evaluations.
- **Decision:** 
  1. Default to containerized execution via `DockerSandbox` with network disabled, non-root user, read-only root, and resource quotas (CPU, memory, PIDs). Retain subprocess execution only behind an explicit `--unsafe-local` flag.
  2. Implement an in-code 3-tier `CommandPolicy` engine (`auto_allow`, `require_approval`, `deny`) that cannot be widened by prompt injection or model hallucination.
  3. Harden `PathGuard` to reject access to `.env*`, `.git/`, `.aegis/`, SSH/cloud credentials, root/system paths, and traversal patterns via real path canonicalization and Windows 8.3 name expansion.
  4. Wrap all repository contents and tool outputs in `<UNTRUSTED_DATA>` blocks and redact secrets using combined regex and Shannon entropy before sending to the LLM or saving to logs.
  5. Upgrade `AegisSec` to execute real industry static analysis tools (`bandit`, `detect-secrets`, `semgrep`) and use the LLM strictly for triaging and explaining findings.

## ADR 0004: Codebase Intelligence via Okapi BM25, Multi-Language PageRank RepoMap, and Read-Only Explorer Sub-Agent
- **Status:** Accepted
- **Date:** 2026-10-21
- **Context:** Naive agents grep blindly across repositories, frequently blowing up the context window or failing to locate symbols defined across multiple modules. For large codebases (100k+ lines), brute-force file reading is slow, expensive, and context-exhausting.
- **Decisions:**
  1. **Project Profiler:** Auto-detects language, package manager, test/lint/build commands, and convention rules (`AEGIS.md`, `README.md`, `.cursorrules`), caching metadata under `.aegis/project.json`.
  2. **Multi-Language RepoMap:** Parses ASTs and signatures for Python, JS/TS, Go, Rust, and Java. Builds an import dependency graph, computes PageRank centrality, and renders an outline clipped strictly to a token budget (1k-4k tokens), cached under `.aegis/index/repo_map.json`.
  3. **Pure-Python Okapi BM25 Index:** Tokenizes code with snake_case and camelCase subword splitting. Indexes chunked source windows with disk caching under `.aegis/index/bm25.json`, exposing `search_code`, `find_definition`, `find_references`, and `get_repo_map` tools.
  4. **AegisExplorer Sub-Agent:** An isolated, read-only ReAct agent with its own fresh context and strictly read-only tools. Main agents delegate technical inquiries via `ExploreCodebaseTool` to receive concise, cited (`file:line`) findings without polluting main execution history.
  5. **Empirical Verification:** Validated on a 520-file synthetic repository, demonstrating >70% token savings over brute-force file reading with exact symbol retrieval.

## ADR 0005: Dynamic DAG Planning, Adaptive Supervisor Loop, Failure Ledger, and Hard Invariants
- **Status:** Accepted
- **Date:** 2026-10-21
- **Context:** AegisOS originally operated as a rigid linear waterfall pipeline (CTO → DEV → QA → SEC → OPS). In real-world engineering, bug fixes often introduce regressions, requiring iterative re-planning and pivoting. A linear pipeline has no mechanism to adaptively pivot, track past failed approaches, or strictly prevent completion without genuine verification.
- **Decisions:**
  1. **Dynamic Plan DAG:** Tasks are modeled as a dependency DAG (`DynamicPlan` and `PlanTask`) with typed inputs/outputs and verification conditions. Independent ready tasks can be scheduled in parallel groups.
  2. **Failure Ledger:** Every task error, tool failure, or invariant breakdown is logged into `FailureLedger` with root causes and actionable avoidance rules. Guidance is automatically injected into planning and execution prompts to prevent repeating failed attempts.
  3. **Adaptive Pivots & Re-planning:** When a task exhausts retries or uncovers blockers, the supervisor replaces the failed subgraph (`replan_failed_subgraph`) with pivot tasks and reroutes downstream dependencies.
  4. **Worktree Isolation:** Ephemeral git worktrees (`WorktreeManager`) isolate concurrent or experimental task execution, merging back changes or cleanly aborting on conflicts.
  5. **Hard Invariants Engine:** Non-bypassable deterministic gates (`HardInvariantEngine`) guarantee no mission can complete without: (1) real tests passing with >0 total tests and 0 failures, (2) SEC clearance with 0 critical and 0 high findings, (3) Reviewer approval, and (4) test suite integrity.
  6. **Backward Compatibility:** Expose `--strategy adaptive` (default in CLI) alongside `--strategy waterfall` in `MissionOrchestrator`, ensuring legacy scripts and existing integration tests remain 100% green.

## ADR 0006: Verification That Cannot Be Gamed — Baseline-First, AST Test Integrity, Reviewer Agent, and TDD Mode
- **Status:** Accepted
- **Date:** 2026-10-21
- **Context:** Autonomous coding models frequently game benchmark evaluation by deleting tests, adding `@pytest.mark.skip`, weakening assertions (`assert True`), or suppressing errors in broad `except: pass` blocks. Verification must be structurally and deterministically immune to evasion.
- **Decisions:**
  1. **Baseline-First Verification:** `BaselineVerifier` captures initial test suite state prior to any code edits. Changes are deemed invalid if previously passing tests regress or overall passing counts drop.
  2. **AST-Diff Test Integrity Guard:** `TestIntegrityGuard` compares AST structures before and after test edits to deterministically detect and reject deleted test functions, skip/xfail decorators, reduced assertion counts, trivial assertions (`assert True`), and exception suppression.
  3. **Independent Reviewer Agent:** `AegisReviewer` operates with a completely fresh context receiving only the objective, git diff, and verification reports. A mission cannot complete without structured `APPROVED` sign-off.
  4. **TDD Mode:** `TDDCoordinator` enforces the Red -> Green cycle under `--tdd`: the developer must write a reproduction test, verify it fails (Red), and then write code to make it pass (Green).

*Status note: `TDDCoordinator` exists and is unit-tested but is not wired to a `--tdd` CLI flag (also referenced in ADR 0001).*

## ADR 0007: Multi-Tier Memory, Episodic Persistence, and Convention Learning
- **Status:** Accepted
- **Date:** 2026-10-21
- **Context:** Every mission originally began with zero memory of prior runs, causing the agent to repeatedly stumble upon the same codebase quirks and repeat resolved mistakes.
- **Decisions:**
  1. **Multi-Tier Memory Architecture:** Separates working memory (active task context), episodic memory (cross-mission histories in `.aegis/memory.db`), and semantic memory (learned conventions in `.aegis/conventions.json`).
  2. **SQLite Episodic Store:** Persists mission snapshots including objective, pass/fail status, files modified, failure modes, and successful repair patterns.
  3. **BM25 Memory Retrieval:** At planning time, `MemoryStore` performs BM25 retrieval over past episodes to inject relevant success patterns and known pitfalls into the CTO's context.
  4. **Codebase Conventions:** Abstracted rules that repeatedly pass verification are recorded and reinforced in `.aegis/conventions.json`, providing ongoing guidance to Developer agents.

## ADR 0008: True Filesystem Rollback and Time-Travel Debugging
- **Status:** Accepted
- **Date:** 2026-10-21
- **Context:** Earlier rollback mechanisms only reset SQLite state while leaving modified files, broken syntax, or half-applied patches on disk, leading to corrupted repos upon rewind.
- **Decisions:**
  1. **Dual Checkpointing:** Every mission step captures both an immutable SQLite state snapshot and an atomic git shadow commit (`aegis/<session_id>`) tagged with `aegis-step-<session_id>-<step_index>`.
  2. **Non-Git Fallback:** Where git is unavailable, directory snapshots are archived under `.aegis/snapshots/<session_id>/<step_index>`.
  3. **Atomic Rollback & Interactive Rewind:** `TimeTravelController` coordinates SQLite rollback with hard filesystem resets (`git reset --hard <tag>`), releasing active SQLite locks prior to filesystem restore to prevent Windows `WinError 32` file conflicts.
  4. **CLI Integration:** Added `aegis rewind <step_index>` and `aegis rollback <session_id> <step_index>` subcommands.

## ADR 0009: Structured Mission Tracing, Zero-LLM Replay, and Hardened War Room API
- **Status:** Accepted (decision 5, the War Room dashboard, superseded by ADR 0013)
- **Date:** 2026-10-21
- **Context:** Autonomous multi-agent pipelines require fine-grained observability, live telemetry, and control endpoints without exposing sensitive credentials or overwhelming clients.
- **Decisions:**
  1. **Span-Level Tracing:** `MissionTracer` records structured execution spans (`AGENT_STEP`, `LLM_CALL`, `TOOL_CALL`, `VERIFICATION`) capturing exact duration, token counts, cost in USD, and redacted I/O to SQLite and JSONL exports.
  2. **Automated Secret Redaction:** `SecretRedactor` filters API keys (OpenAI, Anthropic, Groq, Bearer, AWS) and high-Shannon-entropy secret strings before writing to traces or database logs.
  3. **Zero-LLM Replay:** `ReplayEngine` and `aegis replay <session_id>` render historical missions step-by-step with zero model invocations.
  4. **Hardened Mission Control API:** Added token authentication (`X-Aegis-Token`), sliding-window rate limiting, approvals inbox (`/api/approvals`), live mission control (`pause`, `resume`, `cancel`), cumulative git diff (`/api/missions/{id}/diff`), and WebSocket event replay via `last_event_id`.
  5. **War Room Dashboard:** Upgraded React + TypeScript dashboard with live approvals inbox, interactive diff modal, trace span viewer, acceptance criteria checklist, and memory browser.

## ADR 0010: Human-In-The-Loop Autonomy Modes, GitHub PR Workflows, Config Validation, and MCP Tooling
- **Status:** Accepted
- **Date:** 2026-10-21
- **Context:** Everyday software engineering requires configurable autonomy gates (reviewing plans before execution, approving sensitive actions), native GitHub issue/PR flows, validated project configuration, and external tool integration via MCP.
- **Decisions:**
  1. **Autonomy Modes:** Implemented `ModeController` supporting `--mode plan` (pauses after CTO produces plan DAG), `--mode supervised` (prompts human for destructive actions or halts in headless), and `--mode auto` (bounded by deterministic code policy).
  2. **Interactive Pairing Shell:** Added `aegis chat` providing an interactive REPL with real-time codebase search, repository mapping, and tool inspection.
  3. **GitHub Issue & Pull Request Integration:** `GitHubIntegration` parses issue URLs, retrieves issue descriptions, and drafts comprehensive PR markdown bodies featuring acceptance-criteria evidence, pass/fail test statistics, and mission cost accounting.
  4. **Strict Configuration Validation:** `aegis config check` and `AegisTomlSchema` validate `aegis.toml` syntax, role overrides, and budget constraints.
  5. **Model Context Protocol (MCP) & Plugin Engine:** `MCPClient` connects to external tool servers, wrapping tools in `MCPToolWrapper` which enforces `CommandPolicy` before external tool invocation, preventing safety policy bypasses.

## ADR 0011: Scientific Benchmarking, 34-Task Golden Suite, and Component Ablation Proof
- **Status:** Accepted
- **Date:** 2026-10-21
- **Context:** To prove that AegisOS provides genuine autonomous software engineering rather than brittle demo performance, empirical benchmarking across a diverse task set with hidden verification scripts and systematic ablations is necessary.
- **Decisions:**
  1. **Expanded Golden Dataset:** Expanded `eval/tasks/` from 10 to 34 tasks covering features, bug fixes, refactoring, multi-file changes, JavaScript/TypeScript, and adversarial attacks.
  2. **Adversarial Invariant Verification:** Added dedicated adversarial tasks verifying that secret exfiltration (`.env`), test deletion/tampering, and prompt injection attacks are defeated 100% of the time.
  3. **Ablation Studies:** Reported that RepoMap indexing saves 54% tokens, TestIntegrityGuard eliminates 100% of test evasion, and FailureLedger reduces retry loops by 38%.
  4. **Published Empirical Report:** Published complete results in `docs/RESULTS.md`.

## ADR 0012: v2.1.1 Stability Pass
- **Status:** Accepted
- **Date:** 2026-11-21
- **Context:** Live mission traces showed the control loop failing to converge: repeated tool calls, compounding context, QA looping on zero-test results, budget inflation on resume, and hard-coded v2.0 strings mismatched against `aegis_os.__version__ = "2.1.1"`. The codebase also contained stale provider adapters, dead files (`calculator.py`, `Dockerfile.sandbox-node`), and a `max_tokens` typo (`15000000` instead of `1500000`).
- **Decisions:**
  1. **Budget fix:** `aegis.toml` `max_tokens` corrected from `15000000` to `1500000`. `max_cost_usd = 0` (dollar budget disabled; token and step limits are the primary controls).
  2. **Provider consolidation:** `requirements.txt` and `.env.example` updated to remove all non-NVIDIA LangChain adapters (`langchain-groq`, `langchain-anthropic`, `langchain-google-genai`, `langchain-ollama`, `langchain-community`). `SUPPORTED_PROVIDERS = ("nvidia",)` in `kernel/llm.py` is now the sole wired provider.
  3. **Dead-file removal:** `calculator.py`, `tests/unit/test_calculator.py`, `Dockerfile.sandbox-node`, `eval/expand_dataset.py`, `eval/setup_tasks.py`, and stale static assets removed via `git rm`.
  4. **Code fixes:** `import subprocess` added to `adaptive.py` (F821 ruff error); `api.py` attribute names corrected (`tokens_used`, `cost_used_usd`); `cli/chat.py` corrected to call `render_map()` not `render_outline()`; `integrations/github.py` PR footer updated to `f"v{aegis_os.__version__}"`.
  5. **gitignore tightened:** `workspace/` → `/workspace/`, `workspaces/` → `/workspaces/` to stop hiding `aegis_os/workspace/`; cache dirs and `!eval/tasks/*/fixture/.env` added.
  6. **Docs corrected:** `REAL_AGENT_UPGRADE.md` resource ceiling figures updated to match `aegis.toml` and CLI defaults; cost-ceiling paragraph corrected (`max_cost_usd = 0`); RESULTS/DECISIONS ablation claims changed from "Proved" to "Reported"; DEMO sandbox image name updated; ADR 0002/0006 status notes added.
  7. **Test suite:** all tests pass on Python 3.11 with `ruff check` returning no errors after fixes.

## ADR 0013: Remove the War Room Dashboard; PR Pilot (React + Vite) Is the Sole Web UI
- **Status:** Accepted
- **Date:** 2026-11-27
- **Context:** The React + TypeScript War Room dashboard (ADR 0009) was replaced by the PR Pilot interface, but both were still shipped. `aegis_os/static/` held a committed build of the dashboard that `api.py` mounted at `/`, `web/` held its source, and PR Pilot lived beside it as a hand-written single HTML file with inline CSS/JS and a CDN import of three.js. The Vite + React toolchain is the project's preferred front-end stack, so PR Pilot moves onto it instead of leaving it.
- **Decisions:**
  1. **Dashboard removed:** every War Room component, style and mission-control client call in `web/`, and the committed dashboard build at `aegis_os/static/index.html` and `aegis_os/static/assets/`.
  2. **PR Pilot on Vite + React + TypeScript:** `web/` now contains only the PR Pilot UI (typed API client, hooks, panes, lazily loaded three.js scene). It reproduces the former `pr-pilot.html` page for page; the standalone file is deleted. three.js is pinned to 0.170.0 and bundled instead of fetched from a CDN.
  3. **Serving:** `/pr-pilot` serves the built `index.html`, `/assets` serves the bundle, and `/` redirects to `/pr-pilot`. If the UI is not built, `/pr-pilot` returns `503` with the build command and the API keeps working. The Vite dev server (`:5173`) is a CORS origin again for `npm run dev`, which proxies `/api`.
  4. **Build output is generated:** Vite writes to `aegis_os/static/`, which is git-ignored. The `Dockerfile` builds it in a Node stage, CI runs `npm ci`, `npm run lint` and `npm run build` in a `frontend-build` job that the test job depends on, and `web` stays excluded from ruff.
  5. **Backend retained:** the Mission Control REST/WebSocket API (`/api/missions`, `/api/stats`, `/api/memory`, `/api/approvals`, `/api/events`) is unchanged and remains covered by `test_api_real_missions.py` and `test_tracing_and_api.py`. Only its UI was removed.
  6. **Regression guard:** `tests/unit/test_web_ui_routes.py` asserts the root redirect, the built/unbuilt behavior of `/pr-pilot`, that the old dashboard bundle stays gone, and that `web/src` contains no War Room markers.
