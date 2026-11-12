# Contributing to AegisOS

Thank you for contributing to AegisOS! We welcome contributions to our autonomous agent kernel, codebase intelligence, verification safeguards, and developer interfaces.

---

## 1. Development Principles

1. **Zero Mocks on Evaluated Logic**: Never mock the system under test in benchmarks or verification gates.
2. **Deterministic Safety First**: Security policies and invariants are implemented in Python code, never trusted to prompt instructions alone.
3. **Cross-Platform Compatibility**: All code must execute identically on Windows (PowerShell) and Linux/macOS. Always use `pathlib.Path`.
4. **Strict Typing & Linting**: Code must be 100% clean under `ruff check` and pass `mypy` static type checking.

---

## 2. Setup & Local Development

```powershell
# Clone the repository
git clone https://github.com/saicharan-r02/AegisOS.git
cd AegisOS

# Set up virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# Install in editable mode with development dependencies
pip install -r requirements.txt
pip install -e .

# Run pre-flight health check
aegis doctor

# Run full test suite
pytest tests/ -v
```

---

## 3. Pull Request Guidelines

1. **Branching**: Develop features on descriptive branches branched from `main` or `aegis-v2` (`feat/feature-name`, `fix/bug-name`).
2. **Tests Required**: Every new feature or bug fix must include corresponding unit tests under `tests/unit/`.
3. **Architecture Decisions**: Significant architectural or policy changes must include a corresponding ADR in `docs/DECISIONS.md`.
4. **CI Green**: All GitHub Actions matrix checks (Windows & Linux, Python 3.11 & 3.12) must pass before merging.
