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
