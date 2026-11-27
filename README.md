 <div align="center">

# AegisOS | PR Pilot & Autonomous Engineering Runtime

### From GitHub issue to merged-ready PR, backed by a guarded multi-agent runtime

[![CI](https://github.com/saicharan-r02/AegisOS/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/saicharan-r02/AegisOS/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/Version-2.1.1-00d2ff?style=for-the-badge)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-4a7fdb?style=for-the-badge&logo=python&logoColor=white)](pyproject.toml)
[![Security Policy](https://img.shields.io/badge/Security-In--Code_Sandboxed-d942ff?style=for-the-badge&logo=shield)](SECURITY.md)
[![License](https://img.shields.io/badge/License-MIT-f5b731?style=for-the-badge)](LICENSE)

<p align="center">
  <strong>AegisOS</strong> combines an interactive <strong>PR Pilot</strong> interface with a guarded autonomous engineering runtime. It analyzes GitHub issues, identifies root causes, generates code patches, runs verification, and prepares pull requests through a controlled multi-agent workflow.
</p>

<p align="center">
  <a href="#-quickstart-in-60-seconds">Quickstart</a> ·
  <a href="#-how-pr-pilot-works">How PR Pilot Works</a> ·
  <a href="#-architecture--security">Architecture & Security</a> ·
  <a href="#-cli-command-reference">CLI Reference</a> ·
  <a href="#-documentation-index">Documentation</a>
</p>

</div>

---

## 🛩️ How PR Pilot Works

PR Pilot provides an interface for analyzing GitHub issues, generating proposed solutions, and preparing pull requests through AegisOS.

Start the server:

```powershell
aegis server --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` or navigate to `/pr-pilot`.

### Workflow

1. **Provide a GitHub Issue URL**

   Paste a GitHub issue URL, your optional GitHub username, and any additional code, logs, or issue context.

2. **Analyze & solve the issue**

   The `POST /api/pr-pilot/analyze` endpoint fetches the issue, analyzes its context through the configured NVIDIA NIM provider using `ProviderRouter`, and generates four sections:

   - **Analysis:** Issue classification, summary, root cause, likely affected files, fix plan, risks, and maintainer questions.
   - **Solution:** Proposed patch or diff and verification tests.
   - **PR Guide:** A deterministic 10-step Git workflow personalized with your GitHub username, branch name, and commit commands.
   - **PR Text:** Ready-to-copy PR title, description, commit message, and branch name.

3. **Execute Autonomous Fix & Open PR**

   The `POST /api/pr-pilot/execute` endpoint executes the proposed fix through AegisOS.

   The execution workflow:
   - Shallow-clones the target repository into `workspaces/`.
   - Creates or checks out the designated fix branch.
   - Applies the proposed patch or attempts targeted file edits.
   - Performs available local syntax verification.
   - Creates a local Git commit (`COMMITTED_LOCAL`).
   - Opens a GitHub pull request (`PR_OPENED`) when the required GitHub token and fork configuration are available.

### Example API Request

```bash
curl -X POST http://127.0.0.1:8000/api/pr-pilot/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "issue_url": "https://github.com/OWASP/OpenCRE/issues/1215",
    "github_username": "saicharan-r02"
  }'
```

### API Authentication

`AEGIS_API_TOKEN` is optional.

When configured in `.env`, API requests under `/api/` require the `X-Aegis-Token` header.

The following endpoints are exempt:

- `/api/events` WebSocket
- `/docs`
- Static frontend pages

---

## 🚀 Quickstart in 60 Seconds

### Prerequisites

- Python 3.11 or 3.12
- Git
- Node.js 20 or later for frontend development
- Docker for isolated sandbox execution
- NVIDIA API key for LLM-powered functionality

### 1. Clone the Repository

```powershell
git clone https://github.com/saicharan-r02/AegisOS.git

cd AegisOS
```

### 2. Create a Virtual Environment

For Python 3.11:

```powershell
py -3.11 -m venv .venv
```

Or use Python 3.12:

```powershell
py -3.12 -m venv .venv
```

Activate the environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```powershell
python -m pip install --upgrade pip

python -m pip install -r requirements.txt

python -m pip install -e .
```

### 4. Configure Environment Variables

Create your local environment file:

```powershell
Copy-Item .env.example .env
```

Open `.env` and configure the required credentials.

At minimum, configure your NVIDIA API key:

```env
NVIDIA_API_KEY=your_nvidia_api_key
```

For automatic GitHub pull request creation, configure:

```env
GITHUB_TOKEN=your_github_token
```

Never commit `.env` or expose API keys and repository credentials.

### 5. Build the Sandbox Image

Build the Python execution sandbox once:

```powershell
docker build -f Dockerfile.sandbox-python -t aegis-sandbox-python:latest .
```

Docker-based sandbox execution uses the generated image.

Without Docker, supported commands can use `--unsafe-local`; in-code command policies still apply.

### 6. Run System Diagnostics

```powershell
aegis doctor
```

This performs pre-flight checks for the local environment and configuration.

### 7. Start AegisOS

Run the following command from the repository root:

```powershell
aegis server --host 127.0.0.1 --port 8000
```

### 8. Open the Application

Once the server starts, open the following addresses in your browser:

| Application | URL |
|---|---|
| AegisOS Dashboard | http://127.0.0.1:8000/ |
| PR Pilot | http://127.0.0.1:8000/pr-pilot |
| API Documentation | http://127.0.0.1:8000/docs |

Keep the server terminal running while using AegisOS.

Press `Ctrl+C` in the terminal to stop the server.

**Windows command fallback**

If PowerShell does not recognize the `aegis` command, use the executable installed in your virtual environment:

```powershell
.\.venv\Scripts\aegis.exe server --host 127.0.0.1 --port 8000
```

---

## 🧠 Architecture & Security

AegisOS combines autonomous engineering workflows with execution controls, workspace isolation, verification, and persistent mission state.

### Execution Safety

- Hardened Docker sandbox for isolated command execution.
- Three-tier in-code `CommandPolicy`.
- Command approval requirements for restricted operations.

### Path Security

- `PathGuard` validates workspace paths.
- Blocks access to `.env`, credentials, and sensitive files.
- Prevents parent-directory traversal using `../`.
- Enforces workspace boundaries.

### Verification

- AST-based `TestIntegrityGuard`.
- Detects deleted tests, weakened assertions, and fake assertions.
- Includes a Red → Green TDD coordinator in `aegis_os/verification/tdd.py`.
- The TDD coordinator currently exists as a library component and is not exposed through a CLI flag.

### Rollback & Rewind

- Dual rollback mechanism.
- Restores SQLite checkpoint state from `.aegis/checkpoints.db`.
- Restores Git working-tree files.

### Cross-Mission Memory

- SQLite episodic memory.
- BM25-based convention retrieval.
- Reuses relevant information and previously recorded engineering patterns across missions.

---

## ⚠️ Safe-Use Notes

AegisOS uses configurable execution budgets defined in `aegis.toml`.

Example settings:

```toml
max_tokens = 1500000
max_wall_seconds = 7200.0
```

Role-specific context limits and budget settings are also configurable.

### Security Recommendations

- Never commit `.env`.
- Never expose provider API keys or GitHub tokens.
- Keep `.aegis/` and its checkpoint database local.
- Do not commit `.venv/`.
- Do not commit `.mypy_cache/`.
- Do not commit generated `workspaces/`.
- Review generated patches before merging.
- Verify that execution commands are appropriate for the target repository.
- Keep Docker sandboxing enabled for isolated autonomous execution wherever possible.

---

## 📖 CLI Command Reference

AegisOS provides a CLI for mission execution, diagnostics, codebase analysis, verification, and rollback.

| Subcommand | Description | Example |
|---|---|---|
| `server` | Launch PR Pilot and the AegisOS API server | `aegis server --port 8000` |
| `pr-pilot` | Analyze a GitHub issue, draft a patch, and generate a PR guide | `aegis pr-pilot https://github.com/OWASP/OpenCRE/issues/1215 -u saicharan-r02` |
| `run` | Launch an autonomous closed-loop mission | `aegis run "Fix off-by-one bug" --strategy adaptive` |
| `doctor` | Run pre-flight system and configuration diagnostics | `aegis doctor` |
| `chat` | Start an interactive pairing shell with codebase tools | `aegis chat` |
| `replay` | Replay a mission step-by-step without LLM calls | `aegis replay mission-123 --speed 0.2` |
| `rewind` | Roll back mission state and files to a previous step | `aegis rewind 4` |
| `rollback` | Roll back a specific session to a selected step | `aegis rollback mission-123 2` |
| `status` | Inspect previous missions and execution traces | `aegis status` |
| `audit` | Run a static security scan on a target | `aegis audit -t aegis_os/` |
| `test` | Run QA test verification with diagnosis | `aegis test -t tests/` |

For command-specific options, use:

```powershell
aegis --help
```

Or:

```powershell
aegis <subcommand> --help
```

---

## 📚 Documentation Index

Additional technical documentation is available in the repository.

| Document | Description |
|---|---|
| [Architecture Technical Blueprint](docs/ARCHITECTURE.md) | Overall architecture and system components |
| [Security Policy & Threat Model](SECURITY.md) | Security assumptions, safeguards, and threat model |
| [Real-Agent Upgrade Notes](docs/REAL_AGENT_UPGRADE.md) | Version 2.1.1 real-agent upgrade details |
| [Phase 0 Benchmark Baseline](docs/BASELINE.md) | Initial benchmark baseline |
| [Benchmark Results & Ablation Analysis](docs/RESULTS.md) | Benchmark results and ablation analysis |
| [Evaluation & Dataset Methodology](docs/EVAL.md) | Evaluation methodology and datasets |
| [End-to-End Mission Demo & PR Artifact](docs/DEMO.md) | Mission demonstration and PR artifact |
| [Architecture Decision Records](docs/DECISIONS.md) | ADRs 0001–0011 |
| [Phase 0 Architectural Audit](docs/AUDIT.md) | Initial architectural audit |
| [Contributing Guidelines](CONTRIBUTING.md) | Contribution instructions |
| [Changelog](CHANGELOG.md) | Version history and changes |

---

## 📄 License

AegisOS is licensed under the [MIT License](LICENSE).