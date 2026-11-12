# AegisOS Benchmark Baseline (Phase 0)

**Date:** 2026-10-20  
**Branch:** `aegis-v2`  
**Harness:** `eval/engine.py` (`AegisJudge`)  
**Dataset:** 10 isolated fixture tasks under `eval/tasks/`

## Dataset

| Task | Category | Objective |
| :--- | :--- | :--- |
| `easy-01` | Feature | Implement `add(a, b)`. |
| `easy-02` | Bug fix | Correct multiplication in `calculator.py`. |
| `easy-03` | Bug fix | Correct one-indexed pagination offsets. |
| `easy-04` | Feature | Implement Unicode-safe string reversal. |
| `easy-05` | Feature | Implement punctuation- and case-insensitive palindrome detection. |
| `easy-06` | Refactor | Extract pricing constants and use them. |
| `easy-07` | Bug fix | Deep-merge nested dictionaries. |
| `easy-08` | Feature | Implement URL slugification. |
| `easy-09` | Bug fix | Parse quoted CSV fields containing commas. |
| `easy-10` | Bug fix | Apply Gregorian leap-year rules. |

Each task starts from its own fixture directory. The verifier is installed into the temporary task workspace only after the mission, then executed as a separate subprocess. Verifier scripts are kept outside the fixture so they are not part of the agent's initial workspace.

## Results and limitations

The earlier version of this report claimed a 0/10 solve rate and other aggregate measurements without preserving per-task output. Those numbers are **unverified and are not used as baseline results**.

A fresh live run was attempted on 2026-10-20 with the configured Groq provider. It began `easy-01` but did not return a task result. The process repeatedly retried unavailable model IDs and remained in the agent loop. I manually interrupted it after approximately 3.5 minutes. The remaining nine tasks were not started.

| Metric | Measured result |
| :--- | :--- |
| Tasks with verifier results | 0 of 10; run incomplete |
| Solve rate / Pass@1 | Not measured |
| Steps, tokens, and cost | Not measured; the existing runner does not persist complete usage data |
| Observed wall time | Approximately 3.5 minutes before manual interruption on `easy-01` |
| Observed failure | Repeated 404 fallback attempts; current LLM calls have no configured request timeout |
| Full unit suite | 193 passed in 25.89 seconds on Windows, Python 3.14.2 |

The full suite initially collected 192 tests and had one pre-existing failure: a narrow Rich table hid the security finding description. That display bug was fixed and regression coverage added. The 193-test suite then passed.

Because the live baseline did not produce verifier outcomes, a quantitative solve-rate comparison is not available. Phase 10 must rerun this exact task set with bounded timeouts and save per-run JSON results before reporting improvement.

## Findings to carry forward

1. The provider fallback path can repeatedly spend time retrying unavailable model IDs. Phase 1 must add validated provider configuration, bounded retries, timeouts, and persisted per-call usage.
2. The command tool currently executes on the host without a policy engine. Phase 2 must move execution into the Docker sandbox and deny network access by default.
3. The current orchestrator has no independent reviewer gate or enforced acceptance-criteria evidence. Phases 4 and 5 must add those invariants before missions can finish.
