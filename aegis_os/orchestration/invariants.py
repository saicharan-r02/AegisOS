"""Hard invariants engine that enforces deterministic quality and security gates."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class InvariantResult(BaseModel):
    """Result of evaluating an individual hard invariant."""

    name: str = Field(description="Name of the invariant rule")
    passed: bool = Field(description="True if invariant is satisfied")
    details: str = Field(description="Explanatory diagnostic or failure reason")


class HardInvariantEngine:
    """Enforces non-bypassable completion invariants across all missions.

    Rules:
    - Invariant 1: No mission can succeed without QA passing on real tests.
    - Invariant 2: No mission can succeed without SEC clearance (zero critical/high findings).
    - Invariant 3: No mission can succeed without Reviewer approval.
    - Invariant 4: Any change to test files must be justified and not weaken test coverage.
    """

    @classmethod
    def evaluate(
        cls,
        qa_report: Any | None,
        sec_report: Any | None,
        reviewer_approved: bool = True,
        test_integrity_passed: bool = True,
    ) -> tuple[bool, list[InvariantResult]]:
        """Evaluate all 4 hard invariants against mission reports."""
        results: list[InvariantResult] = []

        # 1. Invariant 1: Real QA Test Pass
        if qa_report is None:
            results.append(
                InvariantResult(
                    name="INVARIANT_1_QA_PASS",
                    passed=False,
                    details="No QA test report available. Missions require automated test verification.",
                )
            )
        else:
            failed = getattr(qa_report, "failed", 0)
            errors = getattr(qa_report, "errors", 0)
            total = getattr(qa_report, "total_tests", 0)
            passed_count = getattr(qa_report, "passed", 0)

            if failed > 0 or errors > 0:
                results.append(
                    InvariantResult(
                        name="INVARIANT_1_QA_PASS",
                        passed=False,
                        details=f"QA tests failing: {failed} failed, {errors} errors.",
                    )
                )
            elif total == 0 and passed_count == 0:
                results.append(
                    InvariantResult(
                        name="INVARIANT_1_QA_PASS",
                        passed=False,
                        details="No tests were executed. At least 1 passing test is required to verify changes.",
                    )
                )
            else:
                results.append(
                    InvariantResult(
                        name="INVARIANT_1_QA_PASS",
                        passed=True,
                        details=f"QA passed: {passed_count} test(s) succeeded with 0 failures.",
                    )
                )

        # 2. Invariant 2: SEC Clearance
        if sec_report is None:
            results.append(
                InvariantResult(
                    name="INVARIANT_2_SEC_CLEARANCE",
                    passed=False,
                    details="No security audit report available. SEC clearance is mandatory.",
                )
            )
        else:
            report_error = getattr(sec_report, "report_error", None)
            summary = getattr(sec_report, "summary", None)
            critical = getattr(summary, "critical", 0) if summary else 0
            high = getattr(summary, "high", 0) if summary else 0

            if report_error:
                results.append(
                    InvariantResult(
                        name="INVARIANT_2_SEC_CLEARANCE",
                        passed=False,
                        details=f"Security audit failed: {report_error}",
                    )
                )
            elif critical > 0 or high > 0:
                results.append(
                    InvariantResult(
                        name="INVARIANT_2_SEC_CLEARANCE",
                        passed=False,
                        details=f"Security audit failed with {critical} CRITICAL and {high} HIGH findings.",
                    )
                )
            else:
                results.append(
                    InvariantResult(
                        name="INVARIANT_2_SEC_CLEARANCE",
                        passed=True,
                        details="Security cleared: 0 CRITICAL and 0 HIGH findings.",
                    )
                )

        # 3. Invariant 3: Reviewer Approval
        if not reviewer_approved:
            results.append(
                InvariantResult(
                    name="INVARIANT_3_REVIEWER_APPROVAL",
                    passed=False,
                    details="Reviewer agent rejected the changes or requested amendments.",
                )
            )
        else:
            results.append(
                InvariantResult(
                    name="INVARIANT_3_REVIEWER_APPROVAL",
                    passed=True,
                    details="Reviewer approved changes.",
                )
            )

        # 4. Invariant 4: Test Integrity Guard
        if not test_integrity_passed:
            results.append(
                InvariantResult(
                    name="INVARIANT_4_TEST_INTEGRITY",
                    passed=False,
                    details="Test tampering detected: tests were deleted, commented out, or bypassed.",
                )
            )
        else:
            results.append(
                InvariantResult(
                    name="INVARIANT_4_TEST_INTEGRITY",
                    passed=True,
                    details="Test integrity verified: test suite is genuine and preserved.",
                )
            )

        all_passed = all(r.passed for r in results)
        return all_passed, results
