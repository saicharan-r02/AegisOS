import json
import re
from typing import Any, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage,BaseMessage,HumanMessage,SystemMessage
from pydantic import BaseModel,ConfigDict,Field
import uuid
from aegis_os.kernel.state import AgentRole,AgentState,MissionStatus,StepRecord
from aegis_os.kernel.state_machine import StateMachine
from aegis_os.tools.base import BaseAegisTool,ToolResult
from aegis_os.tools.registry import ToolRegistry

class AgentIntent(BaseModel):
    """
    Structured model output representing an agent's reasoning turn.
    """
    model_config=ConfigDict(extra="ignore")
    thought: str=Field(default="", description="The reasoning rationale behind the decision.")
    action: Optional[str]=Field(default=None, description="Name of the tool to execute.")
    action_input: dict[str, Any]=Field(default_factory=dict, description="Arguments for the tool.")
    final_answer: Optional[str]=Field(default=None, description="Conclusion if the task is complete.")
    parse_error: Optional[str]=Field(default=None, description="Parsing error message if output was malformed.")

    @property
    def is_finished(self) -> bool:
        """True if the agent has reached a conclusion or has no further actions."""
        return bool(self.final_answer) or (self.action is None and self.parse_error is None)

def parse_agent_response(content: str) -> AgentIntent:
    """
    Extract structured AgentIntent from raw LLM output.
    Handles raw JSON, markdown-wrapped JSON code blocks, and plain text conversational answers.
    Never raises an unhandled exception.
    """
    text=content.strip()
    # 1. Look for ```json ... ``` or ``` ... ``` code blocks
    codeblock_match=re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if codeblock_match:
        block_content=codeblock_match.group(1).strip()
        # If codeblock is tagged as json or begins with {, treat it as JSON
        if block_content.startswith("{") or "```json" in text:
            try:
                data=json.loads(block_content)
                if isinstance(data,dict):
                    return AgentIntent(
                        thought=str(data.get("thought","")),
                        action=data.get("action"),
                        action_input=data.get("action_input",{}) if isinstance(data.get("action_input"),dict) else {},
                        final_answer=data.get("final_answer"),
                    )
            except json.JSONDecodeError as exc:
                return AgentIntent(
                    thought="Failed to parse model JSON block.",
                    parse_error=f"JSONDecodeError: {exc}. Raw content: {block_content[:200]}",
                )

    # 2. Look for outermost { ... }
    brace_match=re.search(r"(\{.*\})", text, re.DOTALL)
    if brace_match:
        raw_json=brace_match.group(1).strip()
        try:
            data=json.loads(raw_json)
            if isinstance(data,dict):
                return AgentIntent(
                    thought=str(data.get("thought","")),
                    action=data.get("action"),
                    action_input=data.get("action_input",{}) if isinstance(data.get("action_input"),dict) else {},
                    final_answer=data.get("final_answer"),
                )
        except json.JSONDecodeError as exc:
            return AgentIntent(
                thought="Failed to parse model JSON block.",
                parse_error=f"JSONDecodeError: {exc}. Raw content: {raw_json[:200]}",
            )

    # 3. Check if text starts with { (intended as JSON but malformed / unclosed)
    if text.startswith("{"):
        try:
            data=json.loads(text)
            if isinstance(data,dict):
                return AgentIntent(
                    thought=str(data.get("thought","")),
                    action=data.get("action"),
                    action_input=data.get("action_input",{}) if isinstance(data.get("action_input"),dict) else {},
                    final_answer=data.get("final_answer"),
                )
        except json.JSONDecodeError as exc:
            return AgentIntent(
                thought="Failed to parse model JSON block.",
                parse_error=f"JSONDecodeError: {exc}. Raw content: {text[:200]}",
            )

    # 4. Fallback: treat plain text response as a final answer
    return AgentIntent(thought="Direct conversational response.",final_answer=text)

class BaseAgent:
    """
    Abstract base class for all specialized AegisOS autonomous agents.
    Executes a bounded ReAct cycle under the supervision of a StateMachine.
    """
    def __init__(self,name: str,role: AgentRole,system_prompt: str,llm: BaseChatModel,state_machine: Optional[StateMachine] = None,tools: Optional[Any] = None,max_steps: int = 20) -> None:
        self.name=name
        self.role=role
        self.system_prompt=system_prompt
        self.llm=llm
        if state_machine is None:
            state=AgentState(session_id=str(uuid.uuid4()),mission_goal=f"{name} Session",status=MissionStatus.RUNNING,active_role=role,max_steps=max_steps)
            self.state_machine=StateMachine(state=state)
        else:
            self.state_machine=state_machine
        self.registry=tools if isinstance(tools,ToolRegistry) else ToolRegistry(tools=tools)

    @property
    def tools(self) -> ToolRegistry:
        """Access the agent's tool registry."""
        return self.registry

    def bind_tool(self, tool: BaseAegisTool, overwrite: bool = False) -> None:
        """Add a tool to the agent's registry."""
        self.registry.register(tool, overwrite=overwrite)

    def format_prompt(self, task: str) -> list[BaseMessage]:
        """
        Build the messages array combining system instructions, tool specs,
        recent step history, and current task objective.
        """
        tools_doc=self.registry.format_tool_descriptions()
        system_instruction=(
            f"{self.system_prompt}\n\n"
            f"You are {self.name} (Role: {self.role.value}).\n\n"
            f"{tools_doc}\n\n"
            "### Response Format:\n"
            "You MUST respond ONLY with a valid JSON object in one of two formats:\n\n"
            "If you need to call a tool:\n"
            "```json\n"
            "{\n"
            '  "thought": "Your reasoning about what to do next.",\n'
            '  "action": "tool_name",\n'
            '  "action_input": { ... }\n'
            "}\n"
            "```\n\n"
            "If you have completed your task or have your final answer:\n"
            "```json\n"
            "{\n"
            '  "thought": "Why the task is complete.",\n'
            '  "final_answer": "Your detailed findings, conclusions, or summary."\n'
            "}\n"
            "```"
        )
        messages: list[BaseMessage]=[SystemMessage(content=system_instruction)]
        recent_steps=self.state_machine.state.step_history[-5:]
        if recent_steps:
            history_lines=["### Recent Execution History:"]
            for step in recent_steps:
                tool_info=f" -> Tool '{step.tool_name}' ({step.status.value})" if step.tool_name else ""
                output_snippet=(
                    f"\n    Observation: {step.tool_result.output[:300]}..."
                    if step.tool_result and step.tool_result.output
                    else ""
                )
                error_snippet=f"\n    Error: {step.error}" if step.error else ""
                history_lines.append(
                    f"- Step {step.step_index} [{step.role.value}]: {step.task_description}{tool_info}{output_snippet}{error_snippet}"
                )
            messages.append(HumanMessage(content="\n".join(history_lines)))

        # Current task instruction
        messages.append(HumanMessage(content=f"Current Objective:\n{task}"))
        return messages

    def step(self,task: str) -> StepRecord:
        """
        Execute one ReAct iteration:
        Reason (Prompt + LLM) -> Act (Tool Selection) -> Observe (Execution & Logging).
        """
        # Ensure state machine has active role set
        if self.state_machine.state.active_role != self.role:
            self.state_machine.transition_role(self.role)
        messages=self.format_prompt(task)
        # 1. Query LLM
        response=self.llm.invoke(messages)
        content=response.content if isinstance(response,AIMessage) else str(response)
        # 2. Parse model intent
        intent=parse_agent_response(str(content))
        # 3. If there was a JSON parsing error, record a failed step to allow self-correction
        if intent.parse_error:
            self.state_machine.begin_step(task_description="Formatting output",role=self.role,)
            return self.state_machine.end_step(error=f"Output parsing error: {intent.parse_error}. Please output valid JSON.")
        # 4. If agent emitted a final answer, complete the step
        if intent.is_finished and not intent.action:
            self.state_machine.begin_step(task_description=intent.thought or "Final task completion",role=self.role,)
            result=ToolResult.ok(output=intent.final_answer or "Task concluded.")
            return self.state_machine.end_step(tool_result=result)
        # 5. Execute action via registered tool
        action_name=intent.action or ""
        tool=self.registry.get(action_name)
        if not tool:
            self.state_machine.begin_step(
                task_description=intent.thought or f"Call {action_name}",
                role=self.role,
                tool_name=action_name,
                tool_args=intent.action_input,
            )
            return self.state_machine.end_step(
                error=f"Tool '{action_name}' does not exist in agent registry. Available: {self.registry.list_names()}"
            )

        # Begin step in state machine
        self.state_machine.begin_step(
            task_description=intent.thought or f"Execute {action_name}",
            role=self.role,
            tool_name=action_name,
            tool_args=intent.action_input,
        )
        # Execute tool safely
        tool_result=tool.run(intent.action_input)
        # Conclude step in state machine
        return self.state_machine.end_step(tool_result=tool_result)
    def run_task(self,task: str,max_iterations: int =10) -> list[StepRecord]:
        """
        Run an autonomous ReAct loop up to max_iterations.
        Stops when the agent outputs a final answer or when the mission terminates.
        """
        records: list[StepRecord]=[]
        for _ in range(max_iterations):
            if self.state_machine.state.is_terminal:
                break

            record=self.step(task)
            records.append(record)
            # If the step was a successful final answer, we are done
            if record.tool_name is None and record.status.value == "SUCCESS":
                break
        return records

    def run(self,task: str,max_iterations: int =10) -> str:
        """
        Run ReAct loop and return the final answer or summary of execution results.
        """
        records=self.run_task(task,max_iterations=max_iterations)
        if records:
            last=records[-1]
            if last.tool_result and last.tool_result.output:
                return last.tool_result.output
            if last.error:
                return f"Execution error: {last.error}"
        return "Task completed with no output."