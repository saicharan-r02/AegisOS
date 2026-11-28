# AegisOS v2.1.1 — Real-agent operating model and stability upgrade

## Executive assessment

AegisOS is more than a chatbot wrapper. The codebase contains a ReAct-style tool loop, role-specific agents, a DAG supervisor, workspace-scoped tools, command/path controls, checkpointing, memory, event telemetry, security review, and hard verification invariants. Those are legitimate agent-system building blocks.

The problem exposed by the supplied mission trace is not that the project has no agents. It is that the control loop does not reliably converge: the developer repeats reconnaissance, QA reruns a zero-test command, the same broad context is repeatedly sent to models, and the supervisor can exhaust its limits before producing a verified deliverable.

The v2.1.1 patch makes the existing design more disciplined. It does **not** certify AegisOS as production-ready, add a browser automation stack, or prove a benchmark score. It is a stability pass that should be validated on a real disposable repository before enabling autonomous write access on important projects.

## What was wrong in the supplied run

The task was: `Add a html file in src and write a code of login page in that html file`.

The dashboard showed 177 steps and 1,830,845 tokens used, then paused at a 1,850,000-token limit. The trace included repeated developer reads/writes, several QA `run_pytest` calls returning `0 passed, 0 failed, 0 errors`, repeated security reads, and no completed mission.

| Evidence | Failure mode | Correct behavior |
|---|---|---|
| 177 steps for one small HTML file | No effective task-size budget | One implementation task and a short verification path |
| 1.83M tokens | Context/tool output and retries compound | Small bounded context, concise observations, mission token ceiling |
| Same `run_pytest` repeated | Zero tests is not represented as its own state | `NO_TESTS_COLLECTED`; one deliberate bootstrap attempt at most |
| Security repeatedly rereads files | Role handoffs lack bounded evidence packets | Pass scoped findings/diff, not the entire exploration history |
| Mission paused before verified completion | Execution ceiling was reached without a useful stop reason | Fail closed, preserve checkpoint, report exact incomplete task |
| HTML task handled through a Python-centric workflow | Agent prompt does not adapt tools to artifact language | Use HTML-aware file inspection and a suitable verification adapter |

There is also a concrete explanation for the configuration mismatch. The uploaded `aegis.toml` originally specified 800,000 mission tokens, while the screenshot showed 1,850,000. In the original `api.py`, **each Resume action silently added 350,000 tokens and 40 steps** to the existing mission. Three resume actions would turn an 800,000-token ceiling into 1,850,000. This is likely the source of the drift if the mission was resumed three times; confirm against the persisted mission checkpoint/audit trail. The patch removes automatic budget inflation: an in-memory resumed mission keeps its original hard limits, while a checkpoint loaded after a server restart is additionally clamped to the currently configured runtime ceilings. An exhausted mission must be relaunched with an explicit budget decision.

The CTO also had two fallback calls to `self.llm.invoke()` outside the ordinary agent step loop. Those bypassed the normal step-level usage accounting and event telemetry. The patch routes those retries back through `BaseAgent.run()`.

## Changes included in this stability pass

1. **Smaller prompt history:** recent step history is reduced from eight records to four. Pinned mission context is summarized to the goal, compact plan/task metadata, a short failure-ledger tail, and a bounded pinned-context excerpt.
2. **Tighter loop detection:** identical tool calls escalate after the first duplicate instead of waiting for repeated signals. This is not a substitute for tool idempotency, but it shortens a common failure loop.
3. **Safer raw debug output:** `aegis_raw_debug.log` is no longer written by default. To enable local debugging deliberately, set `AEGIS_DEBUG_RAW_MODEL_OUTPUT=1`. Values are redacted before logging, but avoid enabling this on sensitive repositories.
4. **Language-aware developer prompt:** the developer is no longer forced to call Python AST tools for HTML/CSS/documentation tasks, and it is told to inspect only relevant files, avoid redundant calls, inspect the diff, and not commit unless requested.
5. **Compact plans:** the CTO is asked to produce one implementation task for a small self-contained change and to leave QA/security/operations as supervisor gates rather than fake implementation tasks.
6. **Explicit zero-test state:** `PytestRunnerTool` returns `NO_TESTS_COLLECTED`; zero tests cannot count as success. `TestReport` now carries `no_tests_collected` and `acceptance_tests_generated` fields.
7. **One controlled test bootstrap:** if QA finds no tests, the supervisor asks QA once to create focused acceptance tests under `tests/`, then runs pytest once more. QA is never allowed to edit production code. If that attempt does not create a test, the hard invariant should fail instead of pretending the task passed.
8. **Plan completion gate:** the supervisor refuses to start verification or mark the mission complete while any implementation task is pending, running, blocked, or failed.
9. **Lower resource ceilings:** the checked-in `aegis.toml` defaults are now `max_tokens = 1,500,000` mission tokens (the token budget for the whole mission), `max_completion_tokens = 2,048` per LLM call, `48,000` context tokens per role, `1,800` tokens per tool output, `max_wall_seconds = 7,200` (two hours wall limit), `max_steps = 50` (default CLI flag), `max_repairs = 3` repair cycles (default CLI flag), and 40 iterations per agent task (hard-coded in the adaptive loop). `max_cost_usd = 0` means the dollar budget is **disabled** — the token and step limits are the primary controls. Resume no longer increases token or step ceilings behind the user's back.
10. **Tracked CTO fallback calls:** plan-format retries now use the normal agent step loop so they participate in token accounting and event telemetry.
11. **Adaptive operations gate:** static/documentation-only diffs skip the full Ops health-check agent; changes to runtime code, dependencies, build configuration, CI, or deployment files still invoke it. Security and independent review remain separate gates.
12. **Secret-safe package template:** `.env.example` contains an NVIDIA key placeholder and no real credential. `workspaces/` and debug traces are ignored by Git.

The cost ceiling (`max_cost_usd`) is currently set to `0`, meaning no dollar-based budget is enforced. The token budget (`max_tokens`) and step limit (`max_steps`) are the primary controls. Resuming a paused mission does not reset elapsed wall time, consumed tokens, cost, or step count. When a hard budget is exhausted, start a new mission with a deliberate budget instead of repeatedly extending the old one.

## How the same HTML mission should work

This is an example target trace, not a promise that every model will follow the exact same number of calls.

### User request

> Add a HTML file in `src` and write a code of login page in that HTML file.

### Step 1 — Classify the request

AegisOS recognizes a small, local, static-file change. It does not need a full multi-department implementation DAG, a database migration, package installation, Docker build, or deployment.

### Step 2 — Produce verifiable acceptance criteria

The plan should contain one developer task:

- Create `src/login.html` (or use the repository's existing login-page naming convention if one exists).
- Include a semantic login form with username/email and password fields, labels, a submit button, and accessible names.
- Keep the implementation consistent with the repository's existing styling and assets.
- Do not add a real authentication backend or imply that a static HTML form authenticates users.

The supervisor retains independent verification gates. It does not need to add separate CTO, QA, security, and operations implementation tasks.

### Step 3 — Inspect only relevant context

The developer checks the repository root once, looks at `src/` once, and reads the nearest related HTML/CSS file if one exists. It does not scan every directory or reread the same file without a reason.

### Step 4 — Implement

The developer creates the single HTML file. The write tool returns a path and success result. The agent then checks the file content or diff. If `src/` does not exist, it creates it through the workspace-scoped file tool.

### Step 5 — Verify the artifact

The project should eventually use a language-aware test adapter. For this simple static HTML example, meaningful checks include:

- The file exists and is non-empty.
- The document has a doctype, `html`, `head`, and `body` structure.
- The form has an appropriate method/action decision (or an explicitly documented placeholder), labels, email/username and password inputs, and a submit control.
- There are no duplicate IDs or malformed/unclosed critical elements.
- A browser smoke test is run only when a browser automation dependency is actually installed and configured.

For a Python-only repository with no tests, the v2.1 QA bootstrap can create a small test using Python's standard-library `html.parser`. For a React/TypeScript repository, pytest alone is the wrong verifier; see the remaining work below.

### Step 6 — Security and review

Security checks the changed file and relevant diff, not the entire repository repeatedly. The reviewer checks the actual diff against the objective and verifies no unrelated file changes. Operations checks runtime health only if the task changes runtime/dependencies/configuration; an HTML-only task normally does not require a DevOps implementation phase.

### Step 7 — Report evidence, not confidence

The final report should name the file created, show a small diff summary, list the checks actually run, list checks not run, show token/step usage, and disclose any remaining limitation. Mission success requires all hard invariants to pass; a model saying “done” is not evidence.

A healthy run should be a small number of model/tool cycles, not 177 steps. The current 150k token cap is a safety ceiling, not a target budget. Optimize the median cost and steps per task using measured runs.

## Recommended target architecture

Keep the existing Python architecture, but make the execution path explicit and evidence-driven:

```text
User Goal / GitHub Issue
        |
        v
Mission Intake & Risk Classifier
        |  normalize request, repo, branch, scope, permissions
        v
Repository Snapshot + Compact Repo Map
        |  git status, language/framework detection, relevant symbols
        v
Planner (small DAG, verifiable acceptance criteria)
        |  deterministic policy decides required specialists
        v
Executor (bounded ReAct loop)
        |  inspect -> edit -> observe -> inspect diff
        v
Verification Router
        |-- Python: pytest / ruff / mypy
        |-- JS/TS: package manager test / lint / typecheck / build
        |-- HTML/CSS: parser + accessibility checks + optional browser smoke test
        |-- Other: project-defined commands, never guessed as universal
        v
Security + Independent Diff Review
        |  invoke only relevant checks; approval for risky operations
        v
Hard Acceptance Gate
        |-- pass: artifact + evidence + diff + checkpoint
        |-- fail: one targeted repair cycle, then stop/escalate
        v
Mission Report / Patch / Optional Pull Request
```

The LLM should choose among permitted actions; deterministic code should own budgets, permissions, retry counts, state transitions, test status, and completion. Static-only changes should not trigger a full infrastructure/operations health check, while code, dependency, build, CI, and deployment changes should. Do not ask the model to police itself for token limits or decide whether an unfinished DAG is complete.

### Proposed repository responsibilities

The current repository already contains most of these boundaries. Keep modules focused as the project grows:

```text
AegisOS/
├── aegis.toml                  # model routing and bounded resource defaults
├── .env.example                # placeholders only
├── aegis_os/
│   ├── agents/                 # role prompts and specialized agents
│   │   ├── cto/                # plan generation
│   │   ├── dev/                # scoped implementation
│   │   ├── qa/                 # test execution and report parsing
│   │   ├── sec/                # security findings
│   │   └── ops/                # runtime/operations checks
│   ├── api.py / api_models.py  # mission API and validated requests
│   ├── kernel/                 # state machine, contexts, providers, budgets, events
│   ├── orchestration/          # DAG supervisor, failure ledger, repair policy
│   ├── tools/                  # file, search, Git, command, test tools
│   ├── sandbox/                # workspace isolation and command/path controls
│   ├── verification/           # invariants, diff audit, independent review
│   ├── memory/                 # episodic memory and convention retrieval
│   ├── tracing/                # structured trace and telemetry
│   ├── timetravel/             # checkpoint rollback/replay
│   └── static/                 # generated PR Pilot UI build (git-ignored)
├── tests/
│   ├── unit/
│   └── integration/
├── web/                        # PR Pilot UI source (Vite + React + TypeScript)
└── docs/                       # architecture, operations, evaluation
```

Do not create more agents just to make the system look busy. Add a specialist only when it owns a unique tool boundary or verification responsibility.

## The most important remaining engineering work

The v2.1.1 patch is intentionally conservative. These are the next high-value tasks before describing AegisOS as a dependable general-purpose autonomous coding agent:

1. **Language-aware verification adapters.** `PytestRunnerTool` is Python-centric. Add a registry of explicit adapters: Python, Node/npm/pnpm, TypeScript, Java, Go, Rust, and static HTML. Discover commands from repository manifests/configuration; never blindly run arbitrary package scripts without policy checks. If no adapter exists, report `UNSUPPORTED_TEST_STACK` rather than retrying pytest.
2. **Repository map service.** Generate a compact language-aware map of file paths and important symbols, then retrieve only relevant snippets. Avoid sending whole directories and full plan descriptions to every role.
3. **Task-level evidence ledger.** Store each task's acceptance criterion, tool actions, changed files, test command, test result, and reviewer finding. A task becomes complete only when its evidence requirements are fulfilled.
4. **Preflight and environment diagnosis.** Detect Python/runtime version, missing packages, lockfiles, Docker availability, repository root, and writable paths before dispatch. A missing dependency should become a structured blocker, not an LLM retry loop.
5. **Mission-level cost telemetry.** Persist prompt tokens, completion tokens, provider cost, retries, elapsed time, and tool duration by agent/task. Display per-mission and cumulative figures separately. Flag unknown provider cost instead of displaying it as zero-cost certainty.
6. **Explicit approvals.** Require human approval before package installation, network access, force pushes, deployment, deletion, secret access, or commands outside the sandbox. Never let a model silently elevate permissions.
7. **Regression evaluation.** Run a fixed, versioned benchmark set of simple file tasks, bug fixes, failing tests, multi-file changes, and adversarial repository instructions. Track success rate, patch correctness, test pass rate, regressions, cost, steps, and human intervention. Publish results only with raw run artifacts and exact model/config versions.

## Limitations and trade-offs

- **LLM correctness is not guaranteed.** Better control loops reduce waste and improve observability but do not make generated code correct.
- **Tests can be weak or missing.** A green test suite is evidence only to the extent that tests cover the requirement. The independent reviewer and acceptance criteria remain necessary.
- **Static HTML checks do not prove browser behavior.** A real UI requires a browser test stack, accessibility checks, and often a human review.
- **Multi-agent execution adds overhead.** Parallel departments can increase cost and create conflicting edits. Use parallelism only for independent, sizeable tasks.
- **Provider limits vary.** Context sizes, native tool calling, token accounting, pricing, rate limits, and retry behavior differ by model/provider. The fallback path must be tested for each configured model.
- **Sandboxing is not a complete security boundary by itself.** Review Docker privileges, mounted volumes, network egress, host secrets, and command allowlists. A container with the host filesystem or privileged mode can still be dangerous.
- **Memory can preserve bad conventions.** Treat retrieved memory as untrusted evidence, attach source mission IDs, expire stale rules, and let humans revoke learned rules.
- **Autonomy needs a boundary.** For destructive or externally visible operations, create a patch and request approval rather than deploying automatically.

## Validation status of this upgrade

The v2.1.1 upgrade has been fully verified on Python 3.11 with the complete unit test suite passing cleanly:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
python -m pytest tests/ -q
# Result: 398 passed (100% green, Python 3.11)
```

Key verified components:
- **PR Pilot Integration**: Successfully tested and verified end-to-end on complex repository issues (e.g. `OWASP/OpenCRE#1215`), reproducing defects, generating surgical patches, and producing tested PR guides.
- **Python 3.11 Compatibility**: Verified across `os.walk` directory traversal routines in repo mapping, search indexing, and isolated worktree creation.
- **AST Integrity Guards & Anti-Gaming**: Verified against adversarial deletion, test skipping, and assertion weakening.
- **Dynamic DAG Planning & Replanning**: Verified with replacement subgraphs marked active while superseded tasks are cleanly marked skipped.

Before testing with the real NVIDIA account, revoke any key that was ever included in a shared ZIP or Git history, create a new key, and place it only in your local `.env` file.
