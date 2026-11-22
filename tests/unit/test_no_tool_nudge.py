"""Regression tests: prose-only replies must not count as a finished Dev/QA task."""
from aegis_os.agents.base_agent import BaseAgent, parse_agent_response
from aegis_os.kernel.state import AgentRole, AgentState, MissionStatus, StepStatus
from aegis_os.kernel.state_machine import StateMachine
from tests.unit.test_base_agent import MockChatModel, _AddTool

TOOL_JSON = '{"thought": "add", "action": "add", "action_input": {"a": 1, "b": 2}}'
PROSE = "Here is the code:\n```python\ndef add(a, b):\n    return a + b\n```"


def _agent(responses, *, requires_tool=True, role=AgentRole.DEV):
    sm = StateMachine(state=AgentState(mission_goal="t", status=MissionStatus.RUNNING))
    agent = BaseAgent(
        name="A", role=role, system_prompt="s",
        llm=MockChatModel(responses=responses), state_machine=sm, tools=[_AddTool()],
    )
    agent.requires_tool_before_finish = requires_tool
    return agent


def test_prose_is_flagged_conversational_but_json_final_is_not():
    assert parse_agent_response(PROSE).conversational is True
    assert parse_agent_response('{"thought": "ok", "final_answer": "done"}').conversational is False


def test_prose_then_tool_call_recovers_after_nudge():
    agent = _agent([PROSE, TOOL_JSON, '{"thought": "done", "final_answer": "ok"}'])
    records = agent.run_task("do it", max_iterations=6)
    assert records[0].status != StepStatus.SUCCESS          # prose was NOT accepted as success
    assert any(r.tool_name == "add" and r.status == StepStatus.SUCCESS for r in records)


def test_prose_forever_fails_honestly_instead_of_faking_success():
    agent = _agent([PROSE] * 10)
    # 2 reminders + 1 honest failure == the state machine's 3-strike stagnation limit
    records = agent.run_task("do it", max_iterations=3)
    assert len(records) == 3
    assert all(r.status != StepStatus.SUCCESS for r in records)
    assert "never called a tool" in (records[-1].error or "")


def test_roles_that_do_not_require_tools_still_accept_prose():
    agent = _agent(["Plan: do X then Y."], requires_tool=False, role=AgentRole.REVIEWER)
    records = agent.run_task("review", max_iterations=3)
    assert records[0].status == StepStatus.SUCCESS
