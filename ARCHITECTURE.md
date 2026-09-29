# AegisOS: Architectural Specification & Technical Blueprint

This document details the architectural design, security models, data contracts, and coordination protocols of **AegisOS: an Autonomous AI Engineering Organization**.

---

## 1. Core Architectural Tenets

AegisOS rejects the industry standard pattern of unbound prompt-in-a-loop agent architectures. It is constructed upon five fundamental principles:

1. **State Machine Governance**: The Language Model proposes *intent*; the deterministic State Machine governs *progression*, step budgets, failure stagnation limits, and role handoffs.
2. **Strict Sandboxed RBAC**: Tools are not universally accessible. Each specialized agent archetype receives a tailored `ToolRegistry` enforcing strict capabilities (e.g. CTO and Sec are strictly read-only; QA is scoped exclusively to `tests/`).
3. **Causal Snapshot Persistence**: State is snapshotted per execution step into a transactional SQLite database configured with **Write-Ahead Logging (WAL)**. Any prior state can be rolled back without data corruption.
4. **Asynchronous Event-Driven Telemetry**: All state shifts, tool executions, and status transitions publish immutable `KernelEvent` instances to an in-memory `EventBus`, completely decoupling execution logic from CLI rendering and logging.
5. **Closed-Loop Feedback Cycles**: Verification is not a terminal checkpoint. Automated test failures from `AegisQA` and vulnerability findings from `AegisSec` are packaged as root-cause diagnostics and dispatched back to `AegisDev` for bounded remediation.

---

## 2. Layered Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Presentation & Telemetry Layer                       │
│      CLI Dispatcher (main.py)  │  AegisDisplay (Rich UI)  │  EventBus       │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                            Orchestration Plane                               │
│              MissionOrchestrator  │  MissionDAG  │  Quality Gates            │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                         Autonomous Agent Plane (RBAC)                       │
│    AegisCTO    │    AegisDev    │    AegisQA    │    AegisSec    │  AegisOps   │
│   (Read-Only)  │   (Code/Git)   │ (Test-Scoped) │  (Read-Only)   │  (SRE/Exec) │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                             Kernel & State Machine                           │
│  StateMachine  │  AgentState & StepRecord  │  CheckpointStore (SQLite WAL)   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                          Deterministic Execution Sandbox                     │
│    PathGuard Traversal Defense  │  SubprocessSandbox (Tree-Kill & Quotas)   │
│                   ToolRegistry & BaseAegisTool (Zero-Crash)                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Subsystem Breakdown

### 3.1 Deterministic Execution Kernel & Sandbox (`aegis_os/sandbox/`)
- **`PathGuard`**: Resolves canonical absolute paths (`Path.resolve()`). Rejects any path attempting traversal outside the designated `workspace_root` (blocking `../`, symlinks, and Windows path anomalies).
- **`ExecutionQuota`**: Enforces strict operational boundaries:
  - `timeout_seconds`: Hard execution duration timeout.
  - `max_memory_mb`: Process memory thresholds.
  - `max_output_bytes`: Output truncation limit (default 100KB) to prevent token buffer saturation.
- **`SubprocessSandbox`**: Executes shell commands with process-tree cleanup (`taskkill /F /T` on Windows or `SIGKILL` process groups on POSIX) on timeout expiration, ensuring hanging processes are never orphaned.
- **`ToolResult` Zero-Crash Guarantee**: All tool invocations wrap execution in `try ... except` handlers, returning structured `ToolResult.fail(error=...)` models rather than propagating unhandled exceptions to the reasoning loop.

---

### 3.2 State Machine, Working Memory & Persistence (`aegis_os/kernel/`)
- **`AgentState`**: Global working memory holding `session_id`, `mission_goal`, `step_history`, `context_variables`, `current_step_index`, and `consecutive_failures`.
- **`StateMachine`**:
  - Validates all status transitions (`PENDING -> RUNNING -> COMPLETED/FAILED/ABORTED`).
  - **Max Steps Budget Guard**: Halts execution if `current_step_index >= max_steps`.
  - **Stagnation Guard**: Halts execution if `consecutive_failures >= stagnation_threshold` (default 3), detecting unresolvable agent loops early.
- **`MissionDAG`**:
  - Directed Acyclic Graph defining inter-task dependencies.
  - DFS-based cycle detection raises `CycleDetectedError` on circular edge insertion.
  - Kahn's algorithm topological sorting (`topological_sort()`) ensures prerequisites execute before dependent tasks.
- **`CheckpointStore`**:
  - SQLite backend using `PRAGMA journal_mode = WAL;` and `busy_timeout = 5000;`.
  - Atomically saves mission, step history, and point-in-time state snapshots per step.
  - Provides causal rollback (`rollback_to_step()`) which purges downstream steps to maintain causal consistency.

---

### 3.3 Multi-Provider LLM & Bounded ReAct Agent (`aegis_os/agents/`)
- **`get_llm()` Factory**: Unified abstraction supporting **OpenAI** (`ChatOpenAI`), **Groq** (`ChatGroq`), and local **Ollama** (`ChatOllama`) via LangChain standard interfaces.
- **`BaseAgent`**:
  - Implements bounded ReAct cycle: Reason (Prompt + LLM) -> Act (Tool Call) -> Observe (Sandbox Result) -> Log.
  - `parse_agent_response()` safely extracts structured `AgentIntent` from raw JSON, markdown-wrapped blocks, or conversational fallbacks without crashing.
  - Injects recent step history and dynamic tool documentation into the prompt context.

---

### 3.4 Autonomous Specialized Departments (`aegis_os/agents/`)

```
                          ┌────────────────────────┐
                          │   Tool Registry Scopes │
                          └───────────┬────────────┘
         ┌───────────────┬────────────┼────────────┬───────────────┐
         ▼               ▼            ▼            ▼               ▼
     [AegisCTO]      [AegisDev]   [AegisQA]    [AegisSec]      [AegisOps]
    - ASTGrep       - ReadFile   - PytestRun  - ReadFile      - ExecuteCmd
    - GitStatus     - WriteFile  - ReadFile   - ListDir       - ReadFile
    - ReadFile      - ListDir    - ListDir    - ASTGrep       - ListDir
                    - ASTGrep    - ASTGrep                    - GitStatus
                    - GitStatus  - WriteFile                  - GitDiff
                    - GitDiff      (tests/ only)
                    - GitCommit
                    - ExecuteCmd
```

1. **`AegisCTO`**: System design and planning. Produces validated `MissionPlan` JSON containing tasks, dependencies, department assignments, and technical risk flags.
2. **`AegisDev`**: Implementation and refactoring. Has full write access to the workspace code and authors Git commits.
3. **`AegisQA`**: Test automation and diagnosis. Runs pytest via `PytestRunnerTool`, parses pass/fail metrics, and outputs structured `TestReport` models with root-cause hypotheses.
4. **`AegisSec`**: OWASP vulnerability scanner. Audits source code for injection, dangerous deserialization, and hardcoded credentials. Outputs structured `SecurityReport` models.
5. **`AegisOps`**: Reliability and environment validation. Runs import sanity checks, package dependency checks, and Git tree hygiene validation.

---

### 3.5 Closed-Loop Mission Orchestrator (`aegis_os/orchestrator/`)
The `MissionOrchestrator` executes a 5-phase mission lifecycle:

1. **Planning Phase**:
   - Dispatches user goal to `AegisCTO.plan_mission(goal)`.
   - Constructs `MissionDAG` and computes topological order.
2. **Execution Phase**:
   - Iterates through topologically sorted tasks.
   - Dispatches tasks to designated departments (`AegisDev`, etc.).
3. **Verification & Closed-Loop Feedback Phase**:
   - Executes `AegisQA.run_and_report()` and `AegisSec.audit()` in parallel.
   - **Quality Gate**:
     - Fails if `qa_report.failed > 0` or `qa_report.errors > 0`.
     - Fails if `sec_report.summary.critical > 0` or `sec_report.summary.high > 0`.
   - If quality gates fail:
     - Checks `repair_cycles < max_repair_cycles` (loop guard).
     - Formats failure diagnostics and root-cause hypotheses into a repair prompt.
     - Dispatches repair prompt to `AegisDev`.
     - Re-enters verification phase upon commit.
4. **Operational Readiness Phase**:
   - Runs `AegisOps.health_check()` to verify package imports and environment sanity.
5. **Finalization Phase**:
   - Concludes mission in `StateMachine`, records repair outcomes, and generates immutable `MissionSummary`.

---

## 4. Threat Model & Defensive Mitigations

| Threat Vector | Attack Scenario | AegisOS Defensive Mitigation |
|---|---|---|
| **Directory Traversal** | Agent invokes `read_file("../../etc/passwd")` or symlink escape. | `PathGuard.resolve_safe_path()` normalizes paths, verifies canonical containment, and raises `PathTraversalError`. |
| **Infinite Execution Loop** | Model outputs repetitive failing tool calls or cyclic feedback. | `StateMachine` stagnation guard triggers on 3 consecutive failures; orchestrator limits repair loops to `max_repair_cycles = 3`. |
| **Resource Exhaustion** | Tool executes `while(true)` or allocates unbound memory. | `SubprocessSandbox` enforces `timeout_seconds` and terminates the entire process tree (`taskkill /F /T`). |
| **Context Window Overflow** | Command returns megabytes of logs or compiler outputs. | Quotas truncate tool stdout/stderr to `max_output_bytes` (100KB) with diagnostic truncation warnings. |
| **Arbitrary Code Modification** | Security or QA agents attempt to edit production code. | Strict tool RBAC excludes write tools from `AegisCTO`, `AegisSec`, and `AegisOps`; `AegisQA` write tool is confined to `tests/`. |
| **Vulnerability Introduction** | Developer agent introduces SQL injection or raw exec. | Mandatory OWASP audit gate in `AegisSec` blocks progression on CRITICAL or HIGH findings. |
