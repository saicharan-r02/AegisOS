# AegisOS — Refactoring Progress Tracker

> Systematic code quality refactoring across all clean repository components.

## 1. Inventory Summary

- **Total Clean Files Discovered**: 305
- **Python Application Source (`aegis_os/`)**: 92
- **Frontend Source (`web/src/`, `web/index.html`)**: 6
- **Tests & Evaluation Python Code (`tests/`, `eval/`)**: 121
- **Documentation (`docs/`, `*.md`)**: 12
- **Configuration & Infrastructure**: 15
- **Golden Benchmark Tasks / Data / Other**: 55

## 2. Baseline Test & Lint Status

- **Pytest Baseline**: 326 passed, 1 skipped, 1 warning (43.52s) - 100% green.
- **Ruff Lint Baseline**: 75 warnings/errors (mostly import sorting, unused imports, unused local vars).
- **Oxlint Frontend Baseline**: 6 warnings in `web/src/App.tsx` (nested components in render).
- **Vite Build Baseline**: Built clean in 773ms.

## 3. Batch Plan & Execution Progress

| Batch | Subsystem / Focus | Files | Status | Notes |
|---|---|---|---|---|
| Batch 1 | Kernel & State (`aegis_os/kernel/`) | 7 | Pending | State, context, checkpoint, events |
| Batch 2 | Sandboxing & Security (`aegis_os/sandbox/`, `aegis_os/security/`) | 9 | Pending | PathGuard, policy, docker/subprocess sandbox, redactor |
| Batch 3 | Intelligence Subsystem (`aegis_os/intelligence/`) | 8 | Pending | LLM router, RepoMap, BM25, providers |
| Batch 4 | Orchestration Subsystem (`aegis_os/orchestration/`) | 8 | Pending | DAG, adaptive supervisor, worktree, invariants |
| Batch 5 | Agents Subsystem (`aegis_os/agents/`) | 12 | Pending | Base agent, CTO, DEV, QA, SEC, OPS |
| Batch 6 | Tools & Verification (`aegis_os/tools/`, `aegis_os/verification/`) | 14 | Pending | AST tools, git tools, filesystem, reviewer, integrity guard |
| Batch 7 | Tracing, Memory, Timetravel & Integrations (`aegis_os/tracing/`, `memory/`, `timetravel/`, `integrations/`) | 10 | Pending | Spans, replay, memory store, shadow git, GitHub |
| Batch 8 | CLI & API (`aegis_os/cli/`, `aegis_os/api*.py`, `config/`) | 9 | Pending | CLI entrypoints, doctor, chat, FastAPI endpoints |
| Batch 9 | Web Dashboard (`web/src/`) | 6 | Pending | Fix nested render components, clean state, typing |
| Batch 10 | Tests & Eval Scripts (`tests/`, `eval/`) | ~30 key test files | Pending | Test cleanliness, unused imports, assertions preserved |
| Batch 11 | Final Verification & Docs | All | Pending | Full suite regression check, ruff, oxlint, vite build |

## 4. Detailed File Inventory & Review Status

### Python App (92 files)

| File Path | Category | Status | Action / Notes |
|---|---|---|---|
| `aegis_os/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/__main__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/agents/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/agents/base_agent.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/agents/cto/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/agents/cto/agent.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/agents/cto/prompts.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/agents/dev/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/agents/dev/agent.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/agents/dev/prompts.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/agents/ops/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/agents/ops/agent.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/agents/ops/prompts.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/agents/qa/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/agents/qa/agent.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/agents/qa/prompts.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/agents/sec/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/agents/sec/agent.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/agents/sec/prompts.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/api.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/api_models.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/cli/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/cli/chat.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/cli/display.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/cli/doctor.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/cli/main.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/config/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/config/validator.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/integrations/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/integrations/github.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/intelligence/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/intelligence/bm25.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/intelligence/explorer.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/intelligence/profiler.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/intelligence/repo_map.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/intelligence/search.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/kernel/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/kernel/checkpoint.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/kernel/context.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/kernel/events.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/kernel/exceptions.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/kernel/llm.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/kernel/loop_guard.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/kernel/providers.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/kernel/state.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/kernel/state_machine.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/mcp/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/mcp/client.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/memory/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/memory/models.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/memory/store.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/orchestration/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/orchestration/adaptive.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/orchestration/invariants.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/orchestration/ledger.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/orchestration/modes.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/orchestration/planner.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/orchestration/worktree.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/sandbox/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/sandbox/base.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/sandbox/docker_sandbox.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/sandbox/path_guard.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/sandbox/policy.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/sandbox/quotas.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/sandbox/subprocess_sandbox.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/security/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/security/redactor.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/security/scanners.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/timetravel/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/timetravel/controller.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/timetravel/shadow.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/tools/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/tools/ast_tools.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/tools/base.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/tools/codebase_tools.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/tools/editing_tools.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/tools/filesystem_tools.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/tools/git_tools.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/tools/output_tools.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/tools/registry.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/tools/syntax.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/tools/terminal_tools.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/tools/test_tools.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/tracing/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/tracing/models.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/tracing/replay.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/tracing/tracer.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/verification/__init__.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/verification/baseline.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/verification/integrity.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/verification/reviewer.py` | Python App | Pending Review | Review and refactor if beneficial |
| `aegis_os/verification/tdd.py` | Python App | Pending Review | Review and refactor if beneficial |

### Frontend (6 files)

| File Path | Category | Status | Action / Notes |
|---|---|---|---|
| `web/index.html` | Frontend | Pending Review | Review and refactor if beneficial |
| `web/src/App.css` | Frontend | Pending Review | Review and refactor if beneficial |
| `web/src/App.tsx` | Frontend | Pending Review | Review and refactor if beneficial |
| `web/src/index.css` | Frontend | Pending Review | Review and refactor if beneficial |
| `web/src/main.tsx` | Frontend | Pending Review | Review and refactor if beneficial |
| `web/vite.config.ts` | Frontend | Pending Review | Review and refactor if beneficial |

### Tests Eval (121 files)

| File Path | Category | Status | Action / Notes |
|---|---|---|---|
| `eval/__init__.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/dataset.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/engine.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/expand_dataset.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/models.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/setup_tasks.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/adv-01-secret-reading/fixture/.env` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/adv-01-secret-reading/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/adv-02-test-deletion/fixture/calculator.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/adv-02-test-deletion/fixture/tests/test_math.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/adv-02-test-deletion/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/adv-03-prompt-injection/fixture/user_profile.md` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/adv-03-prompt-injection/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/adv-04-impossible-task/fixture/contradiction.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/adv-04-impossible-task/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-01/fixture/math_utils.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-01/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-02/fixture/calculator.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-02/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-03/fixture/pagination.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-03/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-04/fixture/string_utils.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-04/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-05/fixture/palindrome.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-05/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-06/fixture/pricing.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-06/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-07/fixture/dict_utils.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-07/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-08/fixture/slugify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-08/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-09/fixture/csv_utils.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-09/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-10/fixture/calendar_utils.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-10/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-11/fixture/fib.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-11/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-12/fixture/date_utils.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-12/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-13/fixture/lists.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-13/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-14/fixture/palindrome.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-14/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-15/fixture/chunker.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/easy-15/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/fix-01/fixture/search.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/fix-01/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/fix-02/fixture/stats.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/fix-02/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/fix-03/fixture/nested.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/fix-03/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/fix-04/fixture/currency.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/fix-04/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/fix-05/fixture/accumulator.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/fix-05/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/js-01/fixture/math.js` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/js-01/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/js-02/fixture/slug.js` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/js-02/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/multifile-01/fixture/auth/middleware.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/multifile-01/fixture/auth/tokens.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/multifile-01/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/multifile-02/fixture/events/broker.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/multifile-02/fixture/events/handlers.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/multifile-02/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/multifile-03/fixture/database/connection.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/multifile-03/fixture/database/repo.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/multifile-03/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/refactor-01/fixture/report.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/refactor-01/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/refactor-02/fixture/user_service.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/refactor-02/fixture/validators.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/refactor-02/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/refactor-03/fixture/math_ops.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/refactor-03/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/refactor-04/fixture/pipeline.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/refactor-04/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/ts-01/fixture/types.ts` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `eval/tasks/ts-01/verify.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/__init__.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/conftest.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/integration/__init__.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/integration/test_e2e_mission.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/__init__.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_adversarial_security.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_ast_tools.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_base_agent.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_calculator.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_checkpoint.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_cli.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_codebase_intelligence.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_command_policy.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_context.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_cross_mission_memory.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_docker_sandbox.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_dynamic_orchestration.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_editing_tools.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_events.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_filesystem_tools.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_git_tools.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_judge.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_llm.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_loop_guard.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_orchestrator.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_output_tools.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_path_guard.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_path_guard_properties.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_phase11_packaging_and_doctor.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_phase9_human_and_integrations.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_providers.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_security_scanners.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_specialized_agents.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_state.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_state_machine.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_subprocess_sandbox.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_test_tools.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_time_travel_rollback.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_tool_base.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_tool_registry.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_tracing_and_api.py` | Tests Eval | Pending Review | Review and refactor if beneficial |
| `tests/unit/test_verification_anti_gaming.py` | Tests Eval | Pending Review | Review and refactor if beneficial |

### Docs (12 files)

| File Path | Category | Status | Action / Notes |
|---|---|---|---|
| `CHANGELOG.md` | Docs | Pending Review | Review and refactor if beneficial |
| `CONTRIBUTING.md` | Docs | Pending Review | Review and refactor if beneficial |
| `docs/ARCHITECTURE.md` | Docs | Pending Review | Review and refactor if beneficial |
| `docs/AUDIT.md` | Docs | Pending Review | Review and refactor if beneficial |
| `docs/BASELINE.md` | Docs | Pending Review | Review and refactor if beneficial |
| `docs/DECISIONS.md` | Docs | Pending Review | Review and refactor if beneficial |
| `docs/DEMO.md` | Docs | Pending Review | Review and refactor if beneficial |
| `docs/EVAL.md` | Docs | Pending Review | Review and refactor if beneficial |
| `docs/RESULTS.md` | Docs | Pending Review | Review and refactor if beneficial |
| `full_master_prompt.md` | Docs | Pending Review | Review and refactor if beneficial |
| `README.md` | Docs | Pending Review | Review and refactor if beneficial |
| `SECURITY.md` | Docs | Pending Review | Review and refactor if beneficial |

### Config Infra (15 files)

| File Path | Category | Status | Action / Notes |
|---|---|---|---|
| `.env.example` | Config Infra | Pending Review | Review and refactor if beneficial |
| `.github/workflows/ci.yml` | Config Infra | Pending Review | Review and refactor if beneficial |
| `aegis.toml` | Config Infra | Pending Review | Review and refactor if beneficial |
| `docker-compose.yml` | Config Infra | Pending Review | Review and refactor if beneficial |
| `Dockerfile` | Config Infra | Pending Review | Review and refactor if beneficial |
| `Dockerfile.sandbox-node` | Config Infra | Pending Review | Review and refactor if beneficial |
| `Dockerfile.sandbox-python` | Config Infra | Pending Review | Review and refactor if beneficial |
| `pyproject.toml` | Config Infra | Pending Review | Review and refactor if beneficial |
| `requirements.txt` | Config Infra | Pending Review | Review and refactor if beneficial |
| `web/.oxlintrc.json` | Config Infra | Pending Review | Review and refactor if beneficial |
| `web/package-lock.json` | Config Infra | Pending Review | Review and refactor if beneficial |
| `web/package.json` | Config Infra | Pending Review | Review and refactor if beneficial |
| `web/tsconfig.app.json` | Config Infra | Pending Review | Review and refactor if beneficial |
| `web/tsconfig.json` | Config Infra | Pending Review | Review and refactor if beneficial |
| `web/tsconfig.node.json` | Config Infra | Pending Review | Review and refactor if beneficial |

### Data Eval Tasks Other (55 files)

| File Path | Category | Status | Action / Notes |
|---|---|---|---|
| `.aegis/checkpoints.db` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `.aegis/checkpoints.db-shm` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `.aegis/checkpoints.db-wal` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `.env` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `.gitignore` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `aegis_os/security/semgrep-rules.yml` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `aegis_os/static/assets/index-BancVqMk.js` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `aegis_os/static/assets/index-DDIbYTkB.css` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `aegis_os/static/index.html` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `aegis_os.egg-info/dependency_links.txt` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `aegis_os.egg-info/entry_points.txt` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `aegis_os.egg-info/PKG-INFO` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `aegis_os.egg-info/SOURCES.txt` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `aegis_os.egg-info/top_level.txt` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `calculator.py` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/adv-01-secret-reading/fixture/readme.txt` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/adv-01-secret-reading/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/adv-02-test-deletion/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/adv-03-prompt-injection/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/adv-04-impossible-task/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/easy-01/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/easy-02/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/easy-03/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/easy-04/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/easy-05/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/easy-06/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/easy-07/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/easy-08/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/easy-09/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/easy-10/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/easy-11/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/easy-12/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/easy-13/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/easy-14/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/easy-15/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/fix-01/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/fix-02/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/fix-03/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/fix-04/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/fix-05/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/js-01/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/js-02/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/multifile-01/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/multifile-02/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/multifile-03/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/refactor-01/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/refactor-02/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/refactor-03/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/refactor-04/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `eval/tasks/ts-01/task.json` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `master_prompt_extracted.txt` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `web/.aegis/checkpoints.db` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `web/.gitignore` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `web/calculator.py` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
| `web/tests/test_calculator.py` | Data Eval Tasks Other | Excluded (Data) | Do not modify benchmark task JSON/data |
