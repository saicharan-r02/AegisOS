from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from aegis_os.agents.cto.agent import AegisCTO,MissionPlan, MissionTask
from aegis_os.agents.dev.agent import AegisDev
from aegis_os.agents.qa.agent import AegisQA,TestReport
from aegis_os.agents.sec.agent import AegisSec,SecurityReport
from aegis_os.agents.ops.agent import AegisOps
from aegis_os.tools.filesystem_tools import WriteFileTool
from aegis_os.tools.test_tools import PytestRunnerTool
from aegis_os.tools.terminal_tools import ExecuteCommandTool
from aegis_os.tools.git_tools import GitCommitTool

class TestSpecializedAgentsRBAC:
    @patch("aegis_os.agents.cto.agent.get_llm")
    def test_aegis_cto_rbac(self,mock_get_llm,tmp_path: Path) -> None:
        mock_get_llm.return_value=MagicMock()
        cto=AegisCTO()
        tools=cto.tools.all_tools()
        tool_names=set(tools.keys())

        assert "ast_grep" in tool_names
        assert "git_status" in tool_names
        assert "read_file" in tool_names

        assert "write_file" not in tool_names
        assert "execute_command" not in tool_names
        assert "git_commit" not in tool_names
        assert "run_pytest" not in tool_names

    @patch("aegis_os.agents.dev.agent.get_llm")
    def test_aegis_dev_rbac(self,mock_get_llm,tmp_path: Path) -> None:
        mock_get_llm.return_value=MagicMock()
        dev=AegisDev(workspace_root=tmp_path)
        tool_names=set(dev.tools.all_tools().keys())
        
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "list_dir" in tool_names
        assert "ast_grep" in tool_names
        assert "git_status" in tool_names
        assert "git_diff" in tool_names
        assert "git_commit" in tool_names
        assert "execute_command" in tool_names

        assert "run_pytest" not in tool_names

    @patch("aegis_os.agents.qa.agent.get_llm")
    def test_aegis_qa_rbac(self,mock_get_llm,tmp_path: Path) -> None:
        mock_get_llm.return_value=MagicMock()
        qa=AegisQA(workspace_root=tmp_path)
        tool_names=set(qa.tools.all_tools().keys())

        assert "run_pytest" in tool_names
        assert "read_file" in tool_names
        assert "list_dir" in tool_names
        assert "ast_grep" in tool_names

        write_tool=qa.tools.get("write_file")
        assert isinstance(write_tool,WriteFileTool)
        assert write_tool.workspace_root==(tmp_path/"tests")

        assert "git_commit" not in tool_names
        assert "execute_command" not in tool_names

    @patch("aegis_os.agents.sec.agent.get_llm")
    def test_aegis_sec_rbac(self,mock_get_llm,tmp_path: Path) -> None:
        mock_get_llm.return_value=MagicMock()
        sec=AegisSec(workspace_root=tmp_path)
        tool_names=set(sec.tools.all_tools().keys())

        assert "read_file" in tool_names
        assert "list_dir" in tool_names
        assert "ast_grep" in tool_names

        assert "write_file" not in tool_names
        assert "git_commit" not in tool_names
        assert "execute_command" not in tool_names
        assert "run_pytest" not in tool_names

    @patch("aegis_os.agents.ops.agent.get_llm")
    def test_aegis_ops_rbac(self,mock_get_llm,tmp_path: Path) -> None:
        mock_get_llm.return_value=MagicMock()
        ops=AegisOps(workspace_root=tmp_path)
        tool_names=set(ops.tools.all_tools().keys())

        assert "read_file" in tool_names
        assert "list_dir" in tool_names
        assert "git_status" in tool_names
        assert "git_diff" in tool_names
        assert "execute_command" in tool_names

        assert "write_file" not in tool_names
        assert "git_commit" not in tool_names
        assert "run_pytest" not in tool_names

class TestSpecializedAgentsParsing:
    @patch("aegis_os.agents.cto.agent.get_llm")
    def test_cto_plan_mission_parsing(self,mock_get_llm) -> None:
        mock_get_llm.return_value=MagicMock()
        cto=AegisCTO()

        sample_json_response="""
        Here is the mission plan:
        ```json
        {
        "mission_title": "Build Auth System",
        "objective": "Implement JWT authentication with OAuth2 fallback",
        "tasks": [
        {
        "task_id": "T001",
        "title": "Create User Model",
        "description": "Add Pydantic user schema and password hashing",
        "assigned_to": "AegisDev",
        "depends_on": [],
        "priority": "HIGH",
        "acceptance_criteria": ["Model validates", "Password hashes with bcrypt"]
        }
        ],
        "risk_flags": ["Ensure salt rounds are >= 12"]
        }
        ```
        """
        plan=cto._parse_mission_plan(sample_json_response)
        assert isinstance(plan,MissionPlan)
        assert plan.mission_title=="Build Auth System"
        assert len(plan.tasks)==1
        assert plan.tasks[0].assigned_to=="AegisDev"
        assert "Ensure salt rounds are >= 12" in plan.risk_flags

    @patch("aegis_os.agents.qa.agent.get_llm")
    def test_qa_report_parsing(self,mock_get_llm,tmp_path: Path) -> None:
        mock_get_llm.return_value=MagicMock()
        qa=AegisQA(workspace_root=tmp_path)

        sample_qa_output="""
        ```json
        {
        "passed": 12,
        "failed": 1,
        "errors": 0,
        "findings": [
        {
        "test_name": "test_auth",
        "error_message": "AssertionError: 401 != 200",
        "root_cause_hypothesis": "Missing bearer token in headers"
        }
        ],
        "recommended_action": "Fix auth headers in request"
        }
        ```
        """
        report=qa._parse_report(sample_qa_output)
        assert isinstance(report,TestReport)
        assert report.passed==12
        assert report.failed==1
        assert len(report.findings)==1
        assert report.findings[0].test_name=="test_auth"

    @patch("aegis_os.agents.sec.agent.get_llm")
    def test_sec_report_parsing(self,mock_get_llm,tmp_path: Path) -> None:
        mock_get_llm.return_value=MagicMock()
        sec=AegisSec(workspace_root=tmp_path)
        
        sample_sec_output="""
        ```json
        {
        "audit_target": "aegis_os/sandbox/",
        "findings": [
        {
        "id": "SEC-001",
        "severity": "HIGH",
        "category": "A03 - Injection",
        "file": "sandbox.py",
        "line": 45,
        "description": "Subprocess called without input sanitation",
        "remediation": "Use shlex.quote"
        }
        ],
        "summary": {
        "critical": 0,
        "high": 1,
        "medium": 0,
        "low": 0,
        "info": 0
        }
        }
        ```
        """
        report=sec._parse_report(sample_sec_output,"aegis_os/sandbox/")
        assert isinstance(report,SecurityReport)
        assert report.audit_target=="aegis_os/sandbox/"
        assert len(report.findings)==1
        assert report.findings[0].severity=="HIGH"
        assert report.summary.high==1