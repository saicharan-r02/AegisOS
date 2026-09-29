from typing import Any,List,Optional
import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage,BaseMessage
from langchain_core.outputs import ChatGeneration,ChatResult
from pydantic import BaseModel,Field
from aegis_os.agents.base_agent import AgentIntent,BaseAgent,parse_agent_response
from aegis_os.kernel.state import AgentRole,AgentState,MissionStatus,StepStatus
from aegis_os.kernel.state_machine import StateMachine
from aegis_os.tools.base import BaseAegisTool,ToolResult

class MockChatModel(BaseChatModel):
    """Deterministic mock LLM that yields responses from a predefined list."""
    responses: list[str]=Field(default_factory=list)
    call_count: int=Field(default=0)

    @property
    def _llm_type(self) -> str:
        return "mock_chat"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self.call_count < len(self.responses):
            content=self.responses[self.call_count]
        else:
            content='{"thought": "Fallback finish", "final_answer": "Finished"}'
        self.call_count+=1
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])


class _CalcArgs(BaseModel):
    a:int=Field(description="First number")
    b:int=Field(description="Second number")

class _AddTool(BaseAegisTool):
    name="add"
    description="Add two numbers"
    args_schema=_CalcArgs

    def _execute(self,args: _CalcArgs) -> ToolResult:
        return ToolResult.ok(output=str(args.a+args.b),metadata={"sum":args.a+args.b})

class TestParseAgentResponse:
    """Tests for extracting AgentIntent from varied LLM outputs."""

    def test_parse_clean_json_tool_action(self) -> None:
        raw='{"thought": "Need to add","action": "add","action_input": {"a": 2, "b": 3}}'
        intent=parse_agent_response(raw)
        assert intent.thought=="Need to add"
        assert intent.action=="add"
        assert intent.action_input=={"a":2,"b":3}
        assert intent.final_answer is None
        assert intent.is_finished is False

    def test_parse_markdown_codeblock_json(self) -> None:
        raw=(
            "Here is my decision:\n"
            "```json\n"
            "{\n"
            '  "thought": "Running tests",\n'
            '  "action": "run_pytest",\n'
            '  "action_input": {"target": "tests/"}\n'
            "}\n"
            "```\n"
            "Let me know if this is ok."
        )
        intent=parse_agent_response(raw)
        assert intent.thought=="Running tests"
        assert intent.action=="run_pytest"
        assert intent.action_input=={"target":"tests/"}
        assert intent.final_answer is None

    def test_parse_final_answer_json(self) -> None:
        raw='{"thought": "All tasks done","final_answer": "Task successfully resolved."}'
        intent=parse_agent_response(raw)
        assert intent.thought=="All tasks done"
        assert intent.action is None
        assert intent.final_answer=="Task successfully resolved."
        assert intent.is_finished is True

    def test_parse_conversational_text_fallback(self) -> None:
        raw="I reviewed the code and everything passes all safety checks."
        intent=parse_agent_response(raw)
        assert intent.final_answer==raw
        assert intent.is_finished is True

    def test_parse_malformed_json_returns_error_intent(self) -> None:
        raw='```json\n{"thought": "Incomplete json", "action": "read_file",\n```'
        intent=parse_agent_response(raw)
        assert intent.parse_error is not None
        assert "JSONDecodeError" in intent.parse_error
        assert intent.is_finished is False

class TestBaseAgentExecution:
    """Tests for single ReAct step execution and autonomous multi-turn loops."""

    def test_single_react_step_tool_dispatch(self) -> None:
        llm=MockChatModel(
            responses=['{"thought": "Add numbers","action": "add","action_input": {"a": 10,"b": 20}}']
        )
        state=AgentState(mission_goal="Compute sum",status=MissionStatus.RUNNING)
        sm=StateMachine(state=state)
        agent=BaseAgent(
            name="AegisDev",
            role=AgentRole.DEV,
            system_prompt="You are a developer.",
            llm=llm,
            state_machine=sm,
            tools=[_AddTool()],
        )

        step_record=agent.step("Calculate 10 + 20")
        assert step_record.step_index==1
        assert step_record.role==AgentRole.DEV
        assert step_record.tool_name=="add"
        assert step_record.status==StepStatus.SUCCESS
        assert step_record.tool_result is not None
        assert step_record.tool_result.output=="30"
        assert sm.state.current_step_index==1

    def test_single_react_step_final_answer(self) -> None:
        llm=MockChatModel(
            responses=[
                '{"thought": "Completed calculation", "final_answer": "The sum is 30."}'
            ]
        )
        state=AgentState(mission_goal="Compute sum",status=MissionStatus.RUNNING)
        sm=StateMachine(state=state)
        agent=BaseAgent(
            name="AegisDev",
            role=AgentRole.DEV,
            system_prompt="You are a developer.",
            llm=llm,
            state_machine=sm,
        )

        step_record=agent.step("What is the result?")
        assert step_record.status==StepStatus.SUCCESS
        assert step_record.tool_name is None
        assert step_record.tool_result is not None
        assert "The sum is 30." in step_record.tool_result.output

    def test_unknown_tool_call_fails_gracefully(self) -> None:
        llm=MockChatModel(
            responses=[
                '{"thought": "Use unknown tool", "action": "delete_database", "action_input": {}}'
            ]
        )
        state=AgentState(mission_goal="Test",status=MissionStatus.RUNNING)
        sm=StateMachine(state=state)
        agent=BaseAgent(
            name="AegisDev",
            role=AgentRole.DEV,
            system_prompt="You are a developer.",
            llm=llm,
            state_machine=sm,
            tools=[_AddTool()],
        )

        step_record=agent.step("Run action")
        assert step_record.status==StepStatus.FAILURE
        assert "does not exist in agent registry" in (step_record.error or "")

    def test_malformed_json_records_step_for_self_correction(self) -> None:
        llm=MockChatModel(
            responses=[
                '```json\n{"thought": "bad json", "action": \n```'
            ]
        )
        state=AgentState(mission_goal="Test",status=MissionStatus.RUNNING)
        sm=StateMachine(state=state)
        agent=BaseAgent(
            name="AegisDev",
            role=AgentRole.DEV,
            system_prompt="You are a developer.",
            llm=llm,
            state_machine=sm,
        )

        step_record=agent.step("Run action")
        assert step_record.status==StepStatus.FAILURE
        assert "Output parsing error" in (step_record.error or "")

    def test_run_task_multi_step_convergence(self) -> None:
        llm=MockChatModel(
            responses=[
                '{"thought": "First compute sum","action": "add","action_input": {"a": 10,"b": 5}}',
                '{"thought": "We have the answer","final_answer": "Calculation complete. Result is 15."}',
            ]
        )
        state=AgentState(mission_goal="Multi-step math",status=MissionStatus.RUNNING)
        sm=StateMachine(state=state)
        agent=BaseAgent(
            name="AegisDev",
            role=AgentRole.DEV,
            system_prompt="You are a developer.",
            llm=llm,
            state_machine=sm,
            tools=[_AddTool()],
        )

        records=agent.run_task("Compute 10 + 5 and report answer",max_iterations=5)
        assert len(records)==2
        assert records[0].tool_name=="add"
        assert records[0].status==StepStatus.SUCCESS
        assert records[1].tool_name is None
        assert records[1].status==StepStatus.SUCCESS
        assert "Calculation complete" in (records[1].tool_result.output if records[1].tool_result else "")

    def test_run_task_hits_max_iterations_cap(self) -> None:
        llm=MockChatModel(
            responses=['{"thought": "Looping","action": "add","action_input": {"a": 1,"b": 1}}']*10
        )
        state=AgentState(mission_goal="Loop test",status=MissionStatus.RUNNING)
        sm=StateMachine(state=state)
        agent=BaseAgent(
            name="AegisDev",
            role=AgentRole.DEV,
            system_prompt="You are a developer.",
            llm=llm,
            state_machine=sm,
            tools=[_AddTool()],
        )

        records=agent.run_task("Endless task",max_iterations=3)
        assert len(records)==3
