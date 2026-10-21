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
- **Status:** Accepted
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







