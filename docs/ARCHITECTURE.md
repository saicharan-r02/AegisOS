# AegisOS Architecture & Technical Blueprint (v2.0)

AegisOS is an enterprise-grade autonomous software-engineering organization coordinating specialized agent roles under deterministic safety policies, codebase intelligence, adaptive DAG planning, and anti-gaming verification.

---

## 1. High-Level System Architecture

```mermaid
graph TD
    User([Developer / CI / GitHub Issue]) --> CLI[Aegis CLI / War Room API]
    CLI --> Supervisor[Adaptive Orchestrator]

    subgraph IntelligencePlane [Codebase Intelligence]
        Profiler[Project Profiler]
        RepoMap[Multi-Language RepoMap]
        BM25[Okapi BM25 Index]
        Explorer[AegisExplorer Sub-Agent]
    end

    subgraph AgentSwarm [Autonomous Department Swarm]
        CTO[AegisCTO: Architecture & Plan DAG]
        DEV[AegisDev: Implementation & Patches]
        QA[AegisQA: Pytest & Verification]
        SEC[AegisSec: OWASP & Static Scanners]
        OPS[AegisOps: SRE & Environment Health]
        REV[AegisReviewer: Independent Review]
    end

    subgraph SandboxingAndSecurity [Deterministic Security Isolation]
        Policy[3-Tier CommandPolicy]
        PathGuard[PathGuard Traversal Defense]
        DockerBox[Docker Container Sandbox]
        Redactor[SecretRedactor]
    end

    subgraph PersistenceAndMemory [Persistence & State Management]
        WAL[SQLite Checkpoints & Spans]
        ShadowGit[Shadow Branch & Tag Snapshots]
        MemStore[Episodic Memory & Conventions]
    end

    Supervisor --> IntelligencePlane
    Supervisor --> AgentSwarm
    AgentSwarm --> SandboxingAndSecurity
    Supervisor --> PersistenceAndMemory
```

---

## 2. Dynamic Adaptive Orchestration Loop

Unlike rigid waterfall pipelines (CTO → DEV → QA → SEC → OPS), the **Adaptive Supervisor (`--strategy adaptive`)** models missions as dependency DAGs, dynamically scheduling tasks and pivoting upon unexpected failures:

```mermaid
sequenceDiagram
    autonumber
    participant Sub as Adaptive Supervisor
    participant CTO as AegisCTO
    participant Dev as AegisDev
    participant Worktree as Git Worktree
    participant Guard as TestIntegrityGuard
    participant Rev as AegisReviewer
    participant Invariants as HardInvariants

    Sub->>CTO: Decompose Objective into Task DAG
    CTO-->>Sub: DynamicPlan (Tasks, Acceptance Criteria)
    loop For Ready Tasks (Parallel or Sequential)
        Sub->>Worktree: Spawn Isolated Git Worktree
        Sub->>Dev: Execute Task in Worktree
        Dev-->>Worktree: Apply Surgical AST Patches
        Worktree-->>Sub: Candidate Workspace Diff
        Sub->>Guard: Inspect AST Test Diffs
        alt Test Tampering Detected
            Guard-->>Sub: REJECT (Test Deletion / Weakened Assertions)
            Sub->>Dev: Pivot / Re-plan with Failure Guidance
        else Integrity Verified
            Guard-->>Sub: PASS
        end
    end
    Sub->>Rev: Clean-Context Final Review
    Rev-->>Sub: APPROVED / REQUEST_CHANGES
    Sub->>Invariants: Enforce Completion Gates
    Invariants-->>Sub: Tests Green + 0 Critical Findings + Rev Approval
    Sub-->>User: Merge Branch & Issue Final PR Report
```

---

## 3. Time-Travel Debugging & Rollback Protocol

Every step captures dual point-in-time snapshots:

```mermaid
flowchart LR
    Step[Step N Executed] --> SaveDB[(SQLite Checkpoint)]
    Step --> CommitGit[Git Shadow Commit]
    CommitGit --> TagGit[Tag: aegis-step-SESS-N]

    subgraph RollbackWorkflow [Rollback / Rewind Command]
        ReqRollback[aegis rewind N] --> CloseDB[Close SQLite Handle]
        CloseDB --> GitReset[git reset --hard tag-N]
        GitReset --> ReopenDB[Reopen SQLite State]
        ReopenDB --> Restored[Byte-Identical Code & State]
    end
```

---

## 4. Role Responsibility Matrix & RBAC

| Role | Responsibility | Allowed Tools | RBAC Access |
| :--- | :--- | :--- | :--- |
| **CTO** | Goal decomposition, DAG creation, tech evaluation | `read_file`, `list_dir`, `get_repo_map`, `search_code` | Read-only |
| **DEV** | Code implementation, refactoring, patch generation | `read_file`, `write_file`, `replace_in_file`, `apply_patch` | Read/Write workspace |
| **QA** | Test generation, runner execution, regression triage | `pytest_runner`, `read_file`, `write_file` (scoped to `tests/`) | Test-scoped write |
| **SEC** | Static analysis (`bandit`, `detect-secrets`, `semgrep`) | `security_scanner`, `read_file`, `list_dir` | Read-only |
| **OPS** | Dependency audit, build checks, git hygiene | `git_status`, `git_diff`, `execute_command` (scoped) | Policy-bounded |
| **Reviewer** | Fresh context objective & diff validation | `read_file`, `git_diff`, `get_acceptance_criteria` | Read-only |
| **Explorer** | Sub-agent codebase inquiry without context pollution | `read_file`, `search_code`, `find_definition`, `get_repo_map` | Read-only |

---

## 5. Directory Layout & Module Structure

```text
AegisOS/
├── aegis_os/
│   ├── agents/          # Department agent archetypes (CTO, Dev, QA, Sec, Ops)
│   ├── cli/             # Rich terminal CLI, display formatting, doctor & chat
│   ├── config/          # Schema validator for aegis.toml
│   ├── intelligence/    # RepoMap, AST parser, PageRank, BM25 search & Explorer
│   ├── integrations/    # GitHub issues & automated PR generation
│   ├── kernel/          # State machine, checkpoint store, event bus & LLM router
│   ├── mcp/             # Model Context Protocol client & plugin engine
│   ├── memory/          # Multi-tier episodic memory & learned conventions
│   ├── orchestration/   # Dynamic DAG planner, worktree manager & adaptive loop
│   ├── sandbox/         # Docker container sandbox, subprocess fallback, policy
│   ├── security/        # SecretRedactor & static analysis scanners
│   ├── timetravel/      # ShadowBranchManager & TimeTravelController
│   ├── tools/           # Base tool contracts, AST tools, filesystem & VCS tools
│   ├── tracing/         # Structured span recording, JSONL export & replay engine
│   └── verification/    # BaselineVerifier, TestIntegrityGuard & AegisReviewer
├── docs/                # Architecture, baseline, results, ADRs & eval docs
├── eval/                # 34-task benchmark suite, golden datasets & judge engine
├── web/                 # Vite + React TypeScript War Room mission control dashboard
└── tests/               # Unit, property, and end-to-end integration test suites
```
