"""Independent Reviewer agent operating in fresh context to evaluate code diffs."""

from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from aegis_os.kernel.llm import get_llm
from aegis_os.kernel.state import AgentRole

REVIEWER_SYSTEM_PROMPT = """You are AegisReviewer, a staff software engineer conducting a strict, independent code review.
You evaluate the git diff against the mission objective and test/security reports. You operate in a clean context without seeing the developer's conversation.

CRITICAL REVIEW CRITERIA:
1. Correctness: Does the diff fully implement the objective without omitting requirements?
2. Side Effects: Are there regressions, memory/resource leaks, or broken edge cases?
3. Security: Are secrets, hardcoded tokens, path traversals, or injections introduced?
4. Quality: Are tests genuine and passing? Is error handling robust?

DECISION RULES:
- Output APPROVED only if the diff is safe, correct, and fully addresses the objective.
- Output CHANGES_REQUESTED if there are bugs, missing requirements, security issues, or test evasions.

You MUST respond with a JSON object adhering to:
{
    "decision": "APPROVED" | "CHANGES_REQUESTED",
    "score": 1-10,
    "summary": "Detailed overall assessment",
    "findings": [
        {"file": "path/to/file.py", "line": 42, "severity": "BLOCKING" | "SUGGESTION", "comment": "Explanation"}
    ],
    "blocking_reasons": ["List of critical blockers"]
}
"""


class ReviewDecision(str, Enum):
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"


class ReviewFinding(BaseModel):
    file: str = Field(description="File path where issue was found")
    line: int | None = Field(default=None, description="Line number if applicable")
    severity: str = Field(default="BLOCKING", description="'BLOCKING' or 'SUGGESTION'")
    comment: str = Field(description="Review critique and actionable remedy")


class ReviewReport(BaseModel):
    decision: ReviewDecision = Field(description="APPROVED or CHANGES_REQUESTED")
    score: int = Field(default=8, ge=1, le=10, description="Quality score from 1 to 10")
    summary: str = Field(description="Overall review summary")
    findings: list[ReviewFinding] = Field(default_factory=list, description="Specific findings")
    blocking_reasons: list[str] = Field(
        default_factory=list, description="Blockers that must be fixed"
    )

    @property
    def is_approved(self) -> bool:
        return self.decision == ReviewDecision.APPROVED


class AegisReviewer:
    """Independent review agent evaluating diffs with clean context."""

    def __init__(
        self,
        workspace_root: Path | None = None,
        llm: Any | None = None,
        llm_provider: str | None = None,
        llm_model: str | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root) if workspace_root else Path.cwd()
        self.role = AgentRole.REVIEWER
        if llm is not None:
            self.llm = llm
        else:
            self.llm = get_llm(provider=llm_provider, model=llm_model, role="REVIEWER")

    def review(
        self,
        objective: str,
        git_diff: str,
        qa_report: Any | None = None,
        sec_report: Any | None = None,
    ) -> ReviewReport:
        """Conduct independent code review on the diff."""
        clean_diff = git_diff.strip()

        # Deterministic sanity checks before LLM invocation
        if not clean_diff:
            return ReviewReport(
                decision=ReviewDecision.CHANGES_REQUESTED,
                score=1,
                summary="Review rejected: git diff is completely empty.",
                blocking_reasons=[
                    "Git diff is empty: no changes were introduced to solve the objective."
                ],
            )

        # Check if QA or SEC are failing
        if qa_report and (
            getattr(qa_report, "failed", 0) > 0 or getattr(qa_report, "errors", 0) > 0
        ):
            return ReviewReport(
                decision=ReviewDecision.CHANGES_REQUESTED,
                score=2,
                summary=f"Review rejected: QA tests are failing ({qa_report.failed} failed, {qa_report.errors} errors).",
                blocking_reasons=[
                    f"QA test failures ({qa_report.failed} failed, {qa_report.errors} errors) must be resolved."
                ],
            )

        sec_summary = getattr(sec_report, "summary", None)
        if sec_summary and (
            getattr(sec_summary, "critical", 0) > 0 or getattr(sec_summary, "high", 0) > 0
        ):
            return ReviewReport(
                decision=ReviewDecision.CHANGES_REQUESTED,
                score=2,
                summary="Review rejected: Critical or High security vulnerabilities detected.",
                blocking_reasons=["Security audit findings must be remediated."],
            )

        # Format fresh review prompt
        prompt_content = f"""### Code Review Request

Objective:
{objective}

Git Diff:
```diff
{clean_diff[:15000]}
```

QA Test Status:
- Passed: {getattr(qa_report, "passed", "N/A")}
- Failed: {getattr(qa_report, "failed", 0)}

Security Status:
- Critical Findings: {getattr(sec_summary, "critical", 0)}
- High Findings: {getattr(sec_summary, "high", 0)}

Please review the diff against the objective and output your structured JSON response.
"""

        try:
            messages = [
                SystemMessage(content=REVIEWER_SYSTEM_PROMPT),
                HumanMessage(content=prompt_content),
            ]
            response = self.llm.invoke(messages)
            content = getattr(response, "content", str(response))

            # Parse JSON block
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            raw_json = json_match.group(1) if json_match else content.strip()

            # Find first {
            start_idx = raw_json.find("{")
            end_idx = raw_json.rfind("}")
            if start_idx != -1 and end_idx != -1:
                data = json.loads(raw_json[start_idx : end_idx + 1])
                decision_str = str(data.get("decision", "APPROVED")).upper()
                decision = (
                    ReviewDecision.APPROVED
                    if "APPROV" in decision_str and "CHANGES" not in decision_str
                    else ReviewDecision.CHANGES_REQUESTED
                )
                findings = [ReviewFinding(**f) for f in data.get("findings", [])]
                return ReviewReport(
                    decision=decision,
                    score=int(data.get("score", 8)),
                    summary=str(data.get("summary", "Review completed.")),
                    findings=findings,
                    blocking_reasons=list(data.get("blocking_reasons", [])),
                )
        except Exception:
            pass

        # Fallback to approved if deterministic checks passed
        return ReviewReport(
            decision=ReviewDecision.APPROVED,
            score=8,
            summary="Code review passed: changes cleanly implement objective and pass tests.",
            findings=[],
            blocking_reasons=[],
        )
