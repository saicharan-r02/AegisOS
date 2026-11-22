"""Fixes for the failure modes seen in real runs: amnesia, repeated writes, hidden errors, bad counts."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from aegis_os.agents.base_agent import (
    NO_CHANGE_MARKER,
    BaseAgent,
    _first_tool_error,
    _progress_summary,
    _summarize_tool_args,
)
from aegis_os.kernel.providers import LangChainProvider
from aegis_os.kernel.state import AgentRole, AgentState, MissionStatus
from aegis_os.kernel.state_machine import StateMachine
from aegis_os.memory.recorder import build_episode
from aegis_os.tools.base import ToolResult
from aegis_os.tools.filesystem_tools import WriteFileTool
from aegis_os.tools.test_tools import PytestRunnerTool
from aegis_os.verification.workspace_audit import ensure_git_workspace
from tests.unit.test_base_agent import MockChatModel


def _agent(responses, tools=()):
    sm = StateMachine(state=AgentState(mission_goal="g", status=MissionStatus.RUNNING))
    agent = BaseAgent(
        name="Dev", role=AgentRole.DEV, system_prompt="s",
        llm=MockChatModel(responses=list(responses)), state_machine=sm, tools=list(tools),
    )
    return agent, sm


def _record(sm, tool, args, output="ok", ok=True):
    sm.begin_step(f"Execute tool call(s): {tool}", role=AgentRole.DEV)
    sm.state.step_history[-1].tool_name = tool
    sm.state.step_history[-1].tool_args = {tool: args}
    sm.end_step(tool_result=ToolResult(success=ok, output=output, error=None if ok else output))


# ------------------------------------------------------------------ the prompt remembers
def test_args_summary_never_echoes_whole_file_bodies():
    summary = _summarize_tool_args({"write_file": {"path": "utils.py", "content": "x" * 5000}})
    assert 'path="utils.py"' in summary and "<5000 chars>" in summary and "xxxxx" not in summary


def test_progress_lists_files_already_written_and_how_often():
    _, sm = _agent([])
    _record(sm, "write_file", {"path": "utils.py", "content": "a"})
    _record(sm, "write_file", {"path": "utils.py", "content": "a"})
    _record(sm, "write_file", {"path": "test_utils.py", "content": "b"})
    _record(sm, "run_pytest", {"target": "."}, output="....\n5 passed in 0.2s")
    lines = _progress_summary(sm.state.step_history)
    assert any("utils.py (written 2x)" in line and "test_utils.py" in line for line in lines)
    assert any("5 passed" in line for line in lines)


def test_prompt_history_contains_tool_arguments_and_progress():
    agent, sm = _agent([])
    _record(sm, "write_file", {"path": "utils.py", "content": "def multiply(a, b): return a*b"},
            output="write_file: Successfully wrote 1 lines to 'utils.py'.")
    history = next(m.content for m in agent.format_prompt("do it") if "Recent Execution History" in str(m.content))
    assert 'Args: write_file(path="utils.py"' in history
    assert "### Already done:" in history and "utils.py" in history


def test_failed_steps_are_not_counted_as_done():
    _, sm = _agent([])
    _record(sm, "write_file", {"path": "bad.py", "content": "x"}, output="write_file: ERROR: nope", ok=False)
    assert _progress_summary(sm.state.step_history) == []


def test_real_tool_error_text_is_surfaced():
    out = "git_status: ERROR: git status failed: fatal: not a git repository"
    assert _first_tool_error(out) == out
    assert _first_tool_error("x: deferred; calls must be independent").startswith("x: deferred")


# ------------------------------------------------------------------ identical rewrites are caught
def test_writing_identical_content_again_is_a_noop_that_says_so(tmp_path: Path):
    tool = WriteFileTool(tmp_path)
    first = tool.run({"path": "utils.py", "content": "x = 1\n"})
    again = tool.run({"path": "utils.py", "content": "x = 1\n"})
    changed = tool.run({"path": "utils.py", "content": "x = 2\n"})
    assert first.success and NO_CHANGE_MARKER not in first.output
    assert again.success and NO_CHANGE_MARKER in again.output
    assert NO_CHANGE_MARKER not in changed.output and (tmp_path / "utils.py").read_text() == "x = 2\n"


def test_repeating_a_noop_write_counts_as_no_progress_and_triggers_reflection(tmp_path: Path):
    call = json.dumps({"thought": "w", "action": "write_file",
                       "action_input": {"path": "utils.py", "content": "x = 1\n"}})
    agent, sm = _agent([call] * 4 + ['{"thought": "done", "final_answer": "ok"}'],
                       tools=[WriteFileTool(tmp_path)])
    records = agent.run_task("write utils.py", max_iterations=6)
    assert NO_CHANGE_MARKER in (records[1].tool_result.output or "")
    assert sm.state.context_variables.get("failure_ledger"), "the loop guard should have fired"


# ------------------------------------------------------------------ honest token accounting
def test_tool_call_replies_are_not_counted_as_one_token():
    class Fake:
        def invoke(self, messages):
            return AIMessage(content="", tool_calls=[
                {"name": "write_file", "id": "1", "args": {"path": "a.py", "content": "y" * 800}}
            ])

    provider = LangChainProvider("nvidia", "m", Fake())
    schema = [{"name": "write_file", "description": "d" * 400, "parameters": {"type": "object"}}]
    usage = provider.complete([HumanMessage(content="hi")], tools=schema).usage
    assert usage.output_tokens >= 150      # ~800 chars of arguments were generated
    assert usage.input_tokens >= 100       # tool schemas are part of every request


# ------------------------------------------------------------------ git workspace
def _git_out(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True).stdout


def test_ensure_git_workspace_initialises_a_fresh_folder(tmp_path: Path):
    ws = tmp_path / "fresh"
    ok, _ = ensure_git_workspace(ws)
    assert ok and "AegisOS baseline" in _git_out(ws, "log", "--oneline")
    assert "__pycache__/" in (ws / ".gitignore").read_text()


def test_ensure_git_workspace_leaves_an_existing_repo_alone(tmp_path: Path):
    ensure_git_workspace(tmp_path)
    head = _git_out(tmp_path, "rev-parse", "HEAD")
    ok, note = ensure_git_workspace(tmp_path)
    assert ok and "existing" in note and _git_out(tmp_path, "rev-parse", "HEAD") == head


def test_a_folder_inside_another_repo_gets_its_own_repo(tmp_path: Path):
    ensure_git_workspace(tmp_path)               # the "parent project"
    child = tmp_path / "workspace"
    ok, _ = ensure_git_workspace(child)
    assert ok and (child / ".git").exists()
    (child / "a.py").write_text("x = 1\n")
    assert "a.py" not in _git_out(tmp_path, "diff", "--name-only")


# ------------------------------------------------------------------ pytest tool + memory
def test_pytest_tool_explains_when_no_tests_exist(tmp_path: Path):
    result = PytestRunnerTool(workspace_root=tmp_path, unsafe_local=True).run({"target": "tests/"})
    assert not result.success and "No tests were collected" in (result.error or "")


def test_pytest_tool_accepts_absolute_paths_inside_the_workspace(tmp_path: Path):
    test_file = tmp_path / "test_ok.py"
    test_file.write_text("def test_ok():\n    assert True\n")
    result = PytestRunnerTool(workspace_root=tmp_path, unsafe_local=True).run({"target": str(test_file)})
    assert result.success and result.metadata["passed"] == 1


def test_memory_episode_captures_outcome_and_failures():
    state = AgentState(mission_goal="Add login", status=MissionStatus.FAILED)
    state.context_variables["invariants"] = [
        {"name": "INVARIANT_1_QA_PASS", "passed": False, "details": "2 tests failed"},
        {"name": "INVARIANT_2_SEC_CLEARANCE", "passed": True, "details": ""},
    ]
    state.context_variables["mission_plan"] = {"tasks": [{"task_id": "T1", "title": "Build form"}]}
    episode = build_episode(state, error="RuntimeError: boom")
    assert episode.success is False and episode.tasks_executed == ["T1: Build form"]
    assert any("2 tests failed" in f for f in episode.failure_modes)
    assert any("boom" in f for f in episode.failure_modes)


# ------------------------------------------------------------------ real run: Dev never saw WHERE its code was broken
def test_failed_write_shows_the_model_the_exact_syntax_error_line(tmp_path: Path):
    agent, _ = _agent([], tools=[WriteFileTool(tmp_path)])
    broken = "class Drive:\n    FWD = 1\n    4WD = 2\n"
    output, _, ok = agent._execute_calls(
        [{"name": "write_file", "args": {"path": "models.py", "content": broken}}]
    )
    assert ok is False
    assert "write_file: ERROR:" in output
    assert "line 3" in output.lower() or "models.py:3" in output.lower() or ":3:" in output, output


def test_stagnation_default_gives_room_to_recover():
    assert AgentState(mission_goal="g").stagnation_threshold == 5


def test_the_next_prompt_after_a_broken_write_contains_the_exact_error(tmp_path: Path):
    """Regression for the real failed mission: Dev rewrote the same broken file 3x without seeing line 3."""
    prompts: list[str] = []

    class Recorder(MockChatModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            prompts.append("\n".join(str(m.content) for m in messages))
            return super()._generate(messages, stop, run_manager, **kwargs)

    bad = json.dumps({
        "thought": "w",
        "action": "write_file",
        "action_input": {"path": "models.py", "content": "class Drive:\n    FWD = 1\n    4WD = 2\n"},
    })
    sm = StateMachine(state=AgentState(mission_goal="g", status=MissionStatus.RUNNING))
    agent = BaseAgent(
        name="Dev",
        role=AgentRole.DEV,
        system_prompt="s",
        llm=Recorder(responses=[bad, '{"thought": "fixed", "final_answer": "ok"}']),
        state_machine=sm,
        tools=[WriteFileTool(tmp_path)],
    )
    agent.run_task("write models.py", max_iterations=3)
    assert len(prompts) >= 2
    second = prompts[1]
    assert "Syntax" in second and ("line 3" in second.lower() or ":3" in second), second[-800:]
