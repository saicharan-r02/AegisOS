# Changelog

All notable changes to AegisOS are documented in this file in accordance with [Keep a Changelog](https://keepachangelog.com/).

---

## [2.1.0] - 2026-11-12 (Stability & Hardening Release)

### Fixed
- **Security scanners on Windows**: Replaced `.exe` scanner invocations (`bandit.exe`, `detect-secrets.exe`, `pip-audit.exe`) with `python -m <module>` using `importlib.util.find_spec()` to work around Windows Application Control Policy that blocks `.exe` binaries in virtual environment `Scripts/` directories.
- **`.env` loading**: Added `load_dotenv()` to `aegis_os/cli/main.py` startup so `NVIDIA_API_KEY` and other secrets are always loaded before CLI commands execute.
- **Doctor API key detection**: `aegis doctor` now reads LLM keys from both `os.getenv()` and `LLMConfig()` (pydantic-settings), correctly reporting configured NVIDIA NIM keys.
- **Ruff lint (90 errors → 0)**: Fixed import ordering, E402 (imports after code), UP007 (deprecated `Union` type hints), F821 (undefined `ToolResult` in registry), and unused variable assignments across the codebase.
- **Frontend static component warnings**: Converted nested React components in `App.tsx` from JSX component tags to render functions (`renderSidebar`, `renderTopbar`, `renderDashboardPage`, etc.) eliminating oxlint `static-components` warnings.
- **Frontend provider sync**: Default provider changed from `groq` to `nvidia`; provider dropdown restricted to NVIDIA NIM (the only supported provider).
- **Stale static assets**: Rebuilt frontend (`npm run build`) and replaced stale `index-BancVqMk.js` / `index-DDIbYTkB.css` with fresh `index-C16pQFwh.css` / `index-CggcdwVI.js`.

### Changed
- **Model fallback chains**: All agent roles now have two-tier fallbacks (primary → fast-flash → lightweight-7b) for improved resilience during NVIDIA NIM cold-starts or quota limits. Added `nv-mistralai/mistral-nemo-12b-instruct` and `mistralai/mistral-7b-instruct-v0.3` as second-tier fallbacks.
- **Retry configuration**: Increased `max_retries` from 2 to 3 and `retry_max_seconds` from 8s to 16s to handle NVIDIA NIM API latency spikes.
- **Ruff exclusions**: Added `eval/tasks`, `.venv`, `node_modules`, `web` to ruff `exclude` list (benchmark fixtures intentionally use non-standard style).

### Removed
- Diagnostic/scratch scripts left from development: `aegis_raw_debug.log`, `diag_groq.py`, `diag_llm.py`, `diag_router.py`, `model.py`, `nvidia.py`, `nvidia_model_test_results.csv`, `nvidia_tool_test.py`, `nvidia_working_models.txt`, `test_nvidia_tools.py`, `full_master_prompt.md`, `master_prompt_extracted.txt`, `scratch/` directory.
- Duplicate test file `tests/test_calculator.py` (kept canonical `tests/unit/test_calculator.py`).
- Stale web files: `web/calculator.py`, `web/tests/`, `web/.aegis/`, `web/src/App.css`.

---

## [2.0.0] - 2026-10-21 (Production Release)

### Added
- **Multi-Provider LLM Router**: Seamless fallback chains across Groq, OpenAI, Anthropic, Gemini, and local OpenAI-compatible endpoints with native function calling and token budgets.
- **Docker Sandboxing**: Default containerized execution with dropped capabilities, read-only root FS, non-root user, and disabled network access.
- **3-Tier CommandPolicy**: Deterministic in-code command authorization (`auto_allow`, `require_approval`, `deny`).
- **Codebase Intelligence**: Multi-language PageRank `RepoMap`, pure-Python Okapi BM25 search index, and read-only `AegisExplorer` sub-agent.
- **Dynamic DAG Planning & Adaptive Supervisor**: Replaced linear waterfall with dynamic task DAG, parallel git worktree isolation, `FailureLedger` feedback, and `HardInvariants`.
- **Anti-Gaming Verification**: `BaselineVerifier`, AST `TestIntegrityGuard` (blocking test deletion, skip markers, assertion weakening), independent `AegisReviewer`, and `--tdd` Red→Green coordinator.
- **Cross-Mission Memory**: SQLite episodic mission store, convention learning, and BM25 experience retrieval.
- **True Filesystem Rollback & Time-Travel**: `ShadowBranchManager` with git shadow commits & tags, dual checkpointing with SQLite, `aegis rollback`, and `aegis rewind`.
- **Structured Tracing & Replay**: Span-level latency, token, and cost tracking with `SecretRedactor`, JSONL export, and `aegis replay` (zero LLM calls).
- **Hardened Mission Control API & War Room Dashboard**: Live approvals inbox, side-by-side diff modal, span trace tree, acceptance checklist, and memory browser.
- **Autonomy Modes & Integrations**: `--mode plan|supervised|auto`, `aegis chat` pairing shell, GitHub issue URL ingestion, automated PR generation, and MCP tool client.
- **Scientific Benchmarking**: Expanded to 34 golden tasks across 6 disciplines with ablation analysis in `docs/RESULTS.md`.
- **Pre-Flight System Diagnostics**: `aegis doctor` and `aegis --version`.

### Changed
- Default strategy upgraded to `--strategy adaptive` with backward-compatible `--strategy waterfall`.
- Subprocess execution moved behind explicit `--unsafe-local` flag.

### Fixed
- Fixed Windows SQLite file-locking `PermissionError` (WinError 32) during rollback filesystem resets.
- Fixed unclosed database connections in multi-department orchestrator.

---

## [1.0.0] - 2026-10-18 (Initial Prototype)
- Initial ReAct multi-agent waterfall pipeline (CTO → DEV → QA → SEC → OPS).
- Basic SQLite checkpoint persistence.
- Initial FastAPI backend and prototype React UI.
