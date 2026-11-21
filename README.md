<div align="center">

# ??? AegisOS ? PR Pilot & Autonomous Engineering Runtime
### From GitHub issue to merged-ready PR, backed by a guarded multi-agent runtime

[![CI](https://github.com/saicharan-r02/AegisOS/actions/workflows/ci.yml/badge.svg)](https://github.com/saicharan-r02/AegisOS/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/Version-2.1.1-00d2ff?style=for-the-badge)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-4a7fdb?style=for-the-badge&logo=python&logoColor=white)](pyproject.toml)
[![Security Policy](https://img.shields.io/badge/Security-In--Code_Sandboxed-d942ff?style=for-the-badge&logo=shield)](SECURITY.md)
[![License](https://img.shields.io/badge/License-MIT-f5b731?style=for-the-badge)](LICENSE)

<p align="center">
  <strong>AegisOS</strong> pairs the interactive <strong>PR Pilot</strong> web interface with a guarded engineering runtime that analyzes GitHub issues, drafts patches and PR guides, and executes branch creation, patching, local verification, commits, and pull requests.
</p>

[Quickstart](#-quickstart-in-60-seconds) ?
[How PR Pilot Works](#-how-pr-pilot-works) ?
[Architecture & Security](#-architecture--security) ?
[CLI Reference](#-cli-command-reference) ?
[Documentation](#-documentation-index)

</div>

---

## 🛩️ How PR Pilot Works

Launch the server (`aegis server --port 8000`) and open `http://127.0.0.1:8000` (or `/pr-pilot`):

1. **Paste a GitHub Issue URL** (plus your optional GitHub username and any extra code or logs).
2. **Analyze & solve issue** (`POST /api/pr-pilot/analyze`): Fetches the issue from GitHub, diagnoses the root cause via NVIDIA NIM (`ProviderRouter`), and generates four tabs:
   - **Analysis**: Issue classification, summary, root cause, likely affected files, fix plan, risks, and maintainer questions.
   - **Solution**: Proposed patch / diff and verification tests.
   - **PR Guide**: 10-step Git workflow personalized with your GitHub username, branch name, and commit commands.
   - **PR Text**: Ready-to-copy PR title, description, commit message, and branch name.
3. **Execute Autonomous Fix & Open PR via AegisOS** (`POST /api/pr-pilot/execute`): Shallow-clones the repo into `workspaces/`, checks out the fix branch, applies the drafted patch, runs syntax checks, commits locally (`COMMITTED_LOCAL`), and opens the GitHub PR (`PR_OPENED`) when `GITHUB_TOKEN` and your fork are configured.

```bash
curl -X POST http://127.0.0.1:8000/api/pr-pilot/analyze \
  -H "Content-Type: application/json" \
  -d '{"issue_url": "https://github.com/OWASP/OpenCRE/issues/1215", "github_username": "saicharan-r02"}'
```

> **Note on API Authentication**: `AEGIS_API_TOKEN` is optional; when set in `.env`, `/api/*` requires the `X-Aegis-Token` header; the `/api/events` WebSocket, `/docs`, and static pages are exempt.

---

## 🚀 Quickstart in 60 Seconds

### 1. Installation & Environment
```powershell
git clone https://github.com/saicharan-r02/AegisOS.git
cd AegisOS

python -m venv .venv
.\.venv\Scripts\activate

python -m pip install -r requirements.txt
python -m pip install -e .

cp .env.example .env
# Edit .env and set NVIDIA_API_KEY (and GITHUB_TOKEN for automatic PR creation)
```

### 2. Build the sandbox image (once)
```powershell
docker build -f Dockerfile.sandbox-python -t aegis-sandbox-python:latest .
```
Without Docker, you can use `aegis run ... --unsafe-local` (in-code command policy still applies).

### 3. Launch PR Pilot & Dashboard
```powershell
aegis doctor
aegis server --port 8000
```

Open `http://127.0.0.1:8000` in your browser.

---

## 🧠 Architecture & Security

- **Execution Safety**: Hardened Docker container + 3-tier in-code `CommandPolicy`
- **Path Security**: `PathGuard` blocking `.env`, credentials, and `../` traversal
- **Verification**: AST `TestIntegrityGuard` (blocks deleted tests & fake assertions); a Red->Green TDD coordinator exists in `aegis_os/verification/tdd.py` as a library component and is not yet exposed as a CLI flag.
- **Rollback & Rewind**: Dual rollback restoring both SQLite state (`.aegis/checkpoints.db`) and git files
- **Cross-Mission Memory**: SQLite episodic memory + BM25 convention retrieval

---

## ⚠️ Safe-Use Notes

Budgets are bounded and configured in `aegis.toml` (e.g. `max_tokens = 1500000`, `max_wall_seconds = 7200.0`, with role context limits and no-cost-cap default). Do not commit `.env`, `.aegis/`, `.mypy_cache/`, `.venv/`, `workspaces/`, provider tokens, or repository credentials. Review generated patches against the target repository before merging.

---

## 📖 CLI Command Reference

| Subcommand | Description | Example |
| :--- | :--- | :--- |
| `server` | Launch PR Pilot & AegisOS API server | `aegis server --port 8000` |
| `pr-pilot` | Analyze a GitHub issue, draft a patch, generate a PR guide | `aegis pr-pilot https://github.com/OWASP/OpenCRE/issues/1215 -u <github-username>` |
| `run` | Launch autonomous closed-loop mission | `aegis run "Fix off-by-one bug" --strategy adaptive` |
| `doctor` | Pre-flight system and key diagnostics | `aegis doctor` |
| `chat` | Interactive pairing shell with codebase tools | `aegis chat` |
| `replay` | Replay mission step-by-step (0 LLM calls) | `aegis replay mission-123 --speed 0.2` |
| `rewind` | Time-travel rollback to step N (state + files) | `aegis rewind 4` |
| `rollback` | Roll back specific session to step N | `aegis rollback mission-123 2` |
| `status` | Inspect past missions and step traces | `aegis status` |
| `audit` | Run static security scan on target | `aegis audit -t aegis_os/` |
| `test` | Run QA test verification with diagnosis | `aegis test -t tests/` |

---

## 📚 Documentation Index

- [Architecture Technical Blueprint](docs/ARCHITECTURE.md)
- [Security Policy & Threat Model](SECURITY.md)
- [v2.1.1 Real-Agent Upgrade Notes](docs/REAL_AGENT_UPGRADE.md)
- [Phase 0 Benchmark Baseline](docs/BASELINE.md)
- [Benchmark Results & Ablation Analysis](docs/RESULTS.md)
- [Evaluation & Dataset Methodology](docs/EVAL.md)
- [End-to-End Mission Demo & PR Artifact](docs/DEMO.md)
- [Architecture Decision Records (ADRs 0001–0011)](docs/DECISIONS.md)
- [Phase 0 Architectural Audit](docs/AUDIT.md)
- [Contributing Guidelines](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

---

## 📄 License

AegisOS is licensed under the [MIT License](LICENSE).
