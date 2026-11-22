"""Unit tests for AegisOS PR Pilot end-to-end analysis, guide generation, and API."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from aegis_os.integrations.github import GitHubIssue
from aegis_os.pr_pilot import (
    analyze_pr_issue,
    build_pr_guide,
    extract_json_object,
    parse_github_issue_url,
    sanitize_username,
)


class TestPRPilot(unittest.TestCase):
    def test_parse_github_issue_url_valid_issue_and_pr(self) -> None:
        self.assertEqual(
            parse_github_issue_url("https://github.com/OWASP/OpenCRE/issues/1215"),
            ("OWASP", "OpenCRE", 1215),
        )
        self.assertEqual(
            parse_github_issue_url("https://github.com/owner/my-repo/pull/42"),
            ("owner", "my-repo", 42),
        )
        self.assertIsNone(parse_github_issue_url("https://example.com/not-github"))

    def test_sanitize_username_defaults_and_strips(self) -> None:
        self.assertEqual(sanitize_username("saicharan-r02"), "saicharan-r02")
        self.assertEqual(sanitize_username("  "), "YOUR-USERNAME")
        self.assertEqual(sanitize_username(None), "YOUR-USERNAME")

    def test_build_pr_guide_has_all_10_steps_with_interpolated_values(self) -> None:
        steps = build_pr_guide(
            owner="OWASP",
            repo="OpenCRE",
            issue_number=1215,
            github_username="saicharan-r02",
            branch="fix-export-inverse-internal-link-type",
            commit="fix(export): use inverse link type for child-to-parent CRE links",
        )
        self.assertEqual(len(steps), 10)
        self.assertEqual(steps[0].step_number, 1)
        self.assertIn("https://github.com/OWASP/OpenCRE/issues/1215", steps[0].command)
        self.assertIn("https://github.com/saicharan-r02/OpenCRE.git", steps[2].command)
        self.assertIn(
            "git checkout -b fix-export-inverse-internal-link-type upstream/main",
            steps[3].command,
        )
        self.assertIn('Fixes #1215', steps[6].command)
        self.assertIn(
            "https://github.com/OWASP/OpenCRE/compare/main...saicharan-r02:fix-export-inverse-internal-link-type?expand=1",
            steps[8].command,
        )

    def test_extract_json_object_handles_fences_and_prose(self) -> None:
        raw = 'Here is the analysis:\n```json\n{"kind": "bug", "difficulty": "easy"}\n```\nDone.'
        parsed = extract_json_object(raw)
        self.assertEqual(parsed["kind"], "bug")
        self.assertEqual(parsed["difficulty"], "easy")

    def test_analyze_pr_issue_with_mocked_llm_returns_complete_result(self) -> None:
        mock_ai = {
            "kind": "bug",
            "difficulty": "medium",
            "summary": "Fixes inverse relationship type in export.",
            "rootCause": "Second add_link reuses forward type.",
            "affected": ["application/database/db.py", "application/tests/db_test.py"],
            "plan": ["Compute opposite()", "Update test_export"],
            "patch": "--- a/application/database/db.py\n+++ b/application/database/db.py",
            "tests": "def test_export_inverse(self): pass",
            "branch": "fix-export-inverse-internal-link-type",
            "commit": "fix(export): use inverse link type for child-to-parent CRE links",
            "prTitle": "fix(export): serialize child-to-parent internal CRE links with inverse type",
            "prBody": "## What\nFix export.\n\nFixes #1215",
            "risks": ["opposite() may return None"],
            "questions": ["Confirm with maintainers"],
        }
        res = analyze_pr_issue(
            issue_url="https://github.com/OWASP/OpenCRE/issues/1215",
            github_username="saicharan-r02",
            issue_text="Issue #1215 details and code...",
            llm_caller=lambda prompt, provider, model: mock_ai,
        )
        self.assertEqual(res.owner, "OWASP")
        self.assertEqual(res.repo, "OpenCRE")
        self.assertEqual(res.issue_number, 1215)
        self.assertEqual(res.github_username, "saicharan-r02")
        self.assertEqual(res.ai_error, "")
        self.assertEqual(res.branch, "fix-export-inverse-internal-link-type")
        self.assertEqual(len(res.guide), 10)
        self.assertEqual(res.analysis["kind"], "bug")

    def test_analyze_pr_issue_graceful_fallback_on_llm_error(self) -> None:
        def failing_llm(prompt: str, provider: str, model: str | None):
            raise RuntimeError("NVIDIA_API_KEY is missing")

        res = analyze_pr_issue(
            issue_url="https://github.com/OWASP/OpenCRE/issues/1215",
            github_username="saicharan-r02",
            issue_text="Issue description",
            llm_caller=failing_llm,
        )
        self.assertIsNone(res.analysis)
        self.assertIn("NVIDIA_API_KEY is missing", res.ai_error)
        self.assertEqual(res.branch, "fix-issue-1215")
        self.assertEqual(len(res.guide), 10)
        self.assertIn("Fixes #1215", res.pr_body)

    def test_analyze_pr_issue_autofetches_when_text_blank(self) -> None:
        gh = MagicMock()
        gh.fetch_issue.return_value = GitHubIssue(
            owner="OWASP",
            repo="OpenCRE",
            number=1215,
            title="Incorrect inverse relationship type",
            body="In db.py, export() uses Contains for both directions.",
            html_url="https://github.com/OWASP/OpenCRE/issues/1215",
            comments=["@SravyaMummana2006: working on a fix"],
        )
        captured_prompts: list[str] = []

        def fake_llm(prompt: str, provider: str, model: str | None):
            captured_prompts.append(prompt)
            return {"kind": "bug", "difficulty": "easy", "summary": "ok", "rootCause": "ok"}

        res = analyze_pr_issue(
            issue_url="https://github.com/OWASP/OpenCRE/issues/1215",
            github_username="saicharan-r02",
            issue_text="",
            github_client=gh,
            llm_caller=fake_llm,
        )
        self.assertTrue(res.fetched_from_github)
        self.assertEqual(len(captured_prompts), 1)
        self.assertIn("Incorrect inverse relationship type", captured_prompts[0])
        self.assertIn("@SravyaMummana2006", captured_prompts[0])


    def test_extract_json_object_handles_think_tags_and_single_quotes(self) -> None:
        raw = "<think>reasoning here</think>\n{'kind': 'bug', 'difficulty': 'medium'}"
        parsed = extract_json_object(raw)
        self.assertEqual(parsed["kind"], "bug")
        self.assertEqual(parsed["difficulty"], "medium")


if __name__ == "__main__":
    unittest.main()
