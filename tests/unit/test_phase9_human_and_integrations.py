"""Unit tests for Phase 9: Autonomy modes, GitHub integration, config validation, and MCP tools."""

from __future__ import annotations

from pathlib import Path

from aegis_os.config.validator import validate_config_file
from aegis_os.integrations.github import GitHubIntegration, GitHubIssue
from aegis_os.mcp.client import MCPClient, MCPToolDefinition
from aegis_os.orchestration.modes import AutonomyMode, ModeController
from aegis_os.sandbox.policy import CommandPolicy
from aegis_os.tools.base import ToolResult
from aegis_os.tools.registry import ToolRegistry


class TestAutonomyModes:
    """Validate behavior of human-in-the-loop gates across autonomy modes."""

    def test_plan_mode_signals_halt(self):
        controller = ModeController(mode=AutonomyMode.PLAN)
        assert controller.should_halt_after_plan() is True

    def test_auto_mode_allows_execution(self):
        controller = ModeController(mode=AutonomyMode.AUTO)
        assert controller.should_halt_after_plan() is False
        assert controller.request_approval(action="write_file", reason="editing code") is True

    def test_supervised_mode_prompts_and_honors_decision(self):
        prompt_answers = {"approve_this": True, "deny_this": False}

        def mock_prompt(action: str, reason: str) -> bool:
            return prompt_answers.get(action, False)

        controller = ModeController(mode=AutonomyMode.SUPERVISED, approval_prompt=mock_prompt)
        assert controller.request_approval("approve_this", "valid reason") is True
        assert controller.request_approval("deny_this", "bad action") is False

    def test_headless_supervised_mode_rejects_without_stdin(self):
        controller = ModeController(mode=AutonomyMode.SUPERVISED, headless=True)
        assert controller.request_approval("run_command", "needs stdin") is False


class TestGitHubIntegration:
    """Validate GitHub issue URL extraction and comprehensive PR body generation."""

    def test_parse_issue_url(self):
        gh = GitHubIntegration()
        url = "https://github.com/saicharan-r02/AegisOS/issues/42"
        parsed = gh.parse_issue_url(url)
        assert parsed == ("saicharan-r02", "AegisOS", 42)

    def test_parse_invalid_issue_url(self):
        gh = GitHubIntegration()
        assert gh.parse_issue_url("https://github.com/not-an-issue") is None

    def test_compose_pr_body_with_evidence_and_metrics(self):
        gh = GitHubIntegration()
        issue = GitHubIssue(
            owner="saicharan-r02",
            repo="AegisOS",
            number=42,
            title="Implement robust pagination",
            body="Fix offset limit bugs",
            html_url="https://github.com/saicharan-r02/AegisOS/issues/42",
        )
        acceptance = [
            {"description": "Offset pagination works", "passed": True, "evidence": "pytest test_pagination.py::test_offset PASSED"},
            {"description": "Zero count returns empty list", "passed": True, "evidence": "test_empty_page PASSED"},
        ]
        test_summary = {"passed": 12, "failed": 0, "total": 12, "duration_sec": 1.45}
        cost_metrics = {"tokens": 8500, "cost_usd": 0.0125, "steps": 6}

        pr_body = gh.compose_pr_body(
            issue=issue,
            goal="Implement robust pagination",
            acceptance_criteria=acceptance,
            test_summary=test_summary,
            cost_metrics=cost_metrics,
        )

        assert "Closes #42 — **Implement robust pagination**" in pr_body
        assert "Offset pagination works" in pr_body
        assert "pytest test_pagination.py::test_offset PASSED" in pr_body
        assert "12/12 passed (0 failed)" in pr_body
        assert "$0.0125" in pr_body
        assert "8,500" in pr_body


class TestConfigValidation:
    """Validate aegis.toml config file parsing and schema validation."""

    def test_validates_repo_aegis_toml(self):
        is_valid, msgs = validate_config_file("aegis.toml")
        assert is_valid is True
        assert any("valid" in m.lower() for m in msgs)

    def test_nonexistent_file_returns_error(self, tmp_path: Path):
        is_valid, msgs = validate_config_file(tmp_path / "missing.toml")
        assert is_valid is False
        assert "does not exist" in msgs[0]

    def test_invalid_syntax_returns_error(self, tmp_path: Path):
        bad_toml = tmp_path / "bad.toml"
        bad_toml.write_text("llm = [unterminated", encoding="utf-8")
        is_valid, msgs = validate_config_file(bad_toml)
        assert is_valid is False
        assert "syntax error" in msgs[0].lower()


class TestMCPAndPlugins:
    """Validate external MCP tool registration and security policy wrapping."""

    def test_mcp_tool_registration_and_execution(self):
        registry = ToolRegistry()
        policy = CommandPolicy()
        client = MCPClient(server_name="test-server", policy=policy)

        def mock_caller(tool_name: str, args: dict) -> ToolResult:
            return ToolResult.ok(f"Result from {tool_name}: {args.get('val')}")

        tool_def = MCPToolDefinition(
            name="external_calculator",
            description="External math tool",
            input_schema={"type": "object", "properties": {"val": {"type": "integer"}}},
        )

        client.register_remote_tool(tool_def, mock_caller, registry)
        assert "external_calculator" in registry

        # Call tool via registry
        res = registry.call("external_calculator", val=42)
        assert res.success is True
        assert "Result from external_calculator: 42" in res.output

    def test_mcp_tool_blocked_on_policy_deny(self):
        registry = ToolRegistry()
        policy = CommandPolicy()  # blocks rm -rf, privilege escalation, etc.
        client = MCPClient(server_name="test-server", policy=policy)

        def mock_caller(tool_name: str, args: dict) -> ToolResult:
            return ToolResult.ok("Should never reach here")

        tool_def = MCPToolDefinition(
            name="sudo",
            description="Destructive external tool",
            input_schema={},
        )

        client.register_remote_tool(tool_def, mock_caller, registry)
        res = registry.call("sudo")
        assert res.success is False
        assert "blocked by security policy" in res.error.lower()
