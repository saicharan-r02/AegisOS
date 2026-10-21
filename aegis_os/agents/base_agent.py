import json
import re
import tempfile
import uuid
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from aegis_os.kernel.context import (
    ContextManager,
    LargeOutputStore,
    RoleContextBudget,
    redact_sensitive_text,
)
from aegis_os.kernel.events import LLMCallCompletedEvent, LLMCallStartedEvent, LLMTokenEvent
from aegis_os.kernel.loop_guard import LoopGuard
from aegis_os.kernel.providers import (
    LLMStreamEvent,
    ProviderRouter,
    estimate_tokens,
    response_usage,
)
from aegis_os.kernel.state import AgentRole, AgentState, MissionStatus, StepRecord, StepStatus
from aegis_os.kernel.state_machine import StateMachine
from aegis_os.tools.base import BaseAegisTool, ToolResult
from aegis_os.tools.output_tools import ReadOutputTool
from aegis_os.tools.registry import ToolRegistry

# â”€â”€ JSON helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _first_json(text: str) -> dict:
    """
    Extract the FIRST complete JSON object from arbitrary text.
    Uses raw_decode so trailing data / multiple JSON blocks are safely ignored.
    Raises json.JSONDecodeError if no valid object is found.
    """
    decoder = json.JSONDecoder()
    stripped = text.strip()
    for i, ch in enumerate(stripped):
        if ch == '{':
            try:
                obj, _ = decoder.raw_decode(stripped, i)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    raise json.JSONDecodeError("No JSON object found", stripped, 0)


class AgentIntent(BaseModel):
    """
    Structured model output representing an agent's reasoning turn.
    """
    model_config=ConfigDict(extra="ignore")
    thought: str=Field(default="", description="The reasoning rationale behind the decision.")
    action: str | None=Field(default=None, description="Name of the tool to execute.")
    action_input: dict[str, Any]=Field(default_factory=dict, description="Arguments for the tool.")
    final_answer: str | None=Field(default=None, description="Conclusion if the task is complete.")
    parse_error: str | None=Field(default=None, description="Parsing error message if output was malformed.")

    @property
    def is_finished(self) -> bool:
        """True if the agent has reached a conclusion or has no further actions."""
        return bool(self.final_answer and self.final_answer.strip())


def _intent_from_data(data: dict[str,Any]) -> AgentIntent:
    intent=AgentIntent(
        thought=str(data.get("thought","")),
        action=data.get("action"),
        action_input=data.get("action_input",{}) if isinstance(data.get("action_input"),dict) else {},
        final_answer=data.get("final_answer"),
    )
    if not intent.action and not (intent.final_answer and intent.final_answer.strip()):
        intent.parse_error="Model returned neither a tool action nor a non-empty final answer."
    return intent

def parse_agent_response(content: str) -> AgentIntent:
    """
    Extract structured AgentIntent from raw LLM output.
    Handles raw JSON, markdown-wrapped JSON, multiple JSON blocks, and plain text.
    Uses raw_decode to safely ignore any trailing data after the first valid JSON.
    Never raises an unhandled exception.
    """
    text = content.strip()
    if not text:
        return AgentIntent(thought="Empty provider response.",parse_error="Model returned empty output.")

    # 1. Try to find a ```json ... ``` code block first
    codeblock_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if codeblock_match:
        block = codeblock_match.group(1).strip()
        if block.startswith("{"):
            try:
                data = _first_json(block)
                return _intent_from_data(data)
            except (json.JSONDecodeError, ValueError) as exc:
                return AgentIntent(
                    thought="Failed to parse JSON code block.",
                    parse_error=f"JSONDecodeError: {exc}. Raw: {block[:200]}",
                )

    # 2. Scan entire text for the first { ... } object (handles inline JSON and "extra data" cases)
    try:
        data = _first_json(text)
        return _intent_from_data(data)
    except (json.JSONDecodeError, ValueError):
        pass

    # 3. Plain conversational response â€” treat as final answer
    return AgentIntent(thought="Direct conversational response.", final_answer=text)

class BaseAgent:
    """
    Abstract base class for all specialized AegisOS autonomous agents.
    Executes a bounded ReAct cycle under the supervision of a StateMachine.
    """
    def __init__(self,name: str,role: AgentRole,system_prompt: str,llm: Any,state_machine: StateMachine | None = None,tools: Any | None = None,max_steps: int = 20,context_manager: ContextManager | None = None) -> None:
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
        role_budget=RoleContextBudget(
            window_tokens=getattr(llm,"context_tokens",32_000),
            max_tool_output_tokens=getattr(llm,"max_tool_output_tokens",2_000),
        )
        self.context_manager=context_manager or ContextManager(
            budgets={role.value:role_budget},
            output_store=LargeOutputStore(
                Path(tempfile.gettempdir())/"aegis-os"/"tool-output"/self.state_machine.state.session_id
            ),
        )
        self.registry.register(ReadOutputTool(self.context_manager.output_store))

    @property
    def tools(self) -> ToolRegistry:
        return self.registry

    def bind_tool(self, tool: BaseAegisTool, overwrite: bool = False) -> None:
        self.registry.register(tool, overwrite=overwrite)

    def format_prompt(self,task: str) -> list[BaseMessage]:
        """
        Build the messages array combining system instructions, tool specs,
        recent step history, and current task objective.
        """
        tools_doc=self.registry.format_tool_descriptions()
        native_tools=(
            isinstance(self.llm,ProviderRouter)
            and self.llm.capabilities.native_tool_calling
            and bool(self.registry)
        )
        if native_tools:
            response_format=(
                "Use the structured tool interface for tool calls. If the task is complete, "
                "respond with a concise final answer. Do not invent tool names or arguments."
            )
        else:
            response_format=(
                "Respond with one JSON object. For a tool call use keys thought, action, and "
                "action_input. To finish, use thought and final_answer."
            )
        system_instruction=(
            f"{self.system_prompt}\n\n"
            f"You are {self.name} (Role: {self.role.value}).\n\n"
            f"{tools_doc}\n\n"
            f"### Response Format:\n{response_format}"
        )
        messages: list[BaseMessage]=[SystemMessage(content=system_instruction)]
        recent_steps=self.state_machine.state.step_history[-5:]
        if recent_steps:
            history_lines=["### Recent Execution History:"]
            for step in recent_steps:
                tool_info=f" -> Tool '{step.tool_name}' ({step.status.value})" if step.tool_name else ""
                output_snippet=(
                    f"\n    Observation: {self.context_manager.store_or_truncate(step.tool_result.output,self.role.value)}"
                    if step.tool_result and step.tool_result.output
                    else ""
                )
                error_snippet=f"\n    Error: {step.error}" if step.error else ""
                history_lines.append(
                    f"- Step {step.step_index} [{step.role.value}]: {step.task_description}{tool_info}{output_snippet}{error_snippet}"
                )
            messages.append(HumanMessage(content="\n".join(history_lines)))

        messages.append(HumanMessage(content=f"Current Objective:\n{task}"))
        pinned_values: dict[str,Any]={"goal":self.state_machine.state.mission_goal}
        for key in ("mission_plan","acceptance_criteria","failure_ledger","pinned_context"):
            if key in self.state_machine.state.context_variables:
                pinned_values[key]=self.state_machine.state.context_variables[key]
        pinned_context=redact_sensitive_text(json.dumps(pinned_values,ensure_ascii=False,default=str))
        return self.context_manager.compact(messages,self.role.value,pinned_context)

    @staticmethod
    def _redact_value(value: Any) -> Any:
        if isinstance(value,str):
            return redact_sensitive_text(value)
        if isinstance(value,dict):
            return {str(key):BaseAgent._redact_value(item) for key,item in value.items()}
        if isinstance(value,list):
            return [BaseAgent._redact_value(item) for item in value]
        return value

    def _invoke_llm(
        self,
        messages: Sequence[BaseMessage],
        on_stream_event: Callable[[LLMStreamEvent], None] | None = None,
    ) -> tuple[AIMessage,dict[str,Any]]:
        schemas=self.registry.to_json_schemas()
        if isinstance(self.llm,ProviderRouter):
            result=self.llm.complete(
                messages,
                tools=schemas if schemas else None,
                on_event=on_stream_event,
            )
            usage=result.usage
            return result.message,{
                "provider":usage.provider,
                "model":usage.model,
                "input_tokens":usage.input_tokens,
                "output_tokens":usage.output_tokens,
                "total_tokens":usage.total_tokens,
                "latency_ms":usage.latency_ms,
                "cost_usd":usage.cost_usd,
            }

        model=self.llm
        binder=getattr(model,"bind_tools",None)
        if schemas and callable(binder):
            try:
                model=binder(schemas,parallel_tool_calls=True)
            except (NotImplementedError,TypeError):
                try:
                    model=binder(schemas)
                except NotImplementedError:
                    model=self.llm
        response=model.invoke(list(messages))
        if not isinstance(response,AIMessage):
            response=AIMessage(content=str(getattr(response,"content",response)))
        input_tokens,output_tokens=response_usage(response)
        input_tokens=input_tokens if input_tokens is not None else estimate_tokens(messages)
        output_tokens=output_tokens if output_tokens is not None else estimate_tokens(str(response.content))
        return response,{
            "provider":"legacy",
            "model":"unknown",
            "input_tokens":input_tokens,
            "output_tokens":output_tokens,
            "total_tokens":input_tokens+output_tokens,
            "latency_ms":0.0,
            "cost_usd":None,
        }

    def _execute_calls(self,calls: list[dict[str,Any]]) -> tuple[str,dict[str,Any],bool]:
        validated: list[tuple[str,dict[str,Any],Any]]=[]
        for call in calls:
            name=str(call.get("name") or "")
            args=call.get("args",{})
            if not isinstance(args,dict):
                args={}
            tool=self.registry.get(name)
            validated.append((name,args,tool))
        if len(validated)>1 and all(tool is not None and tool.parallel_safe for _,_,tool in validated):
            with ThreadPoolExecutor(max_workers=min(8,len(validated))) as pool:
                results=list(pool.map(lambda item:item[2].run(item[1]),validated))
            labels=[item[0] for item in validated]
        else:
            first=validated[:1]
            results=[tool.run(args) if tool is not None else None for _,args,tool in first]
            labels=[name for name,_,_ in first]
            if len(validated)>1:
                results.append(None)
                labels.extend(name for name,_,_ in validated[1:])
        output_parts: list[str]=[]
        succeeded=True
        for name,result in zip(labels,results):
            if result is None:
                succeeded=False
                output_parts.append(f"{name}: deferred; calls must be independent and marked parallel-safe.")
            elif result.success:
                output_parts.append(f"{name}: {result.output}")
            else:
                succeeded=False
                output_parts.append(f"{name}: ERROR: {result.error}")
        args_summary={name:args for name,args,_ in validated}
        return "\n".join(output_parts),args_summary,succeeded

    def step(self,task: str) -> StepRecord:
        """
        Execute one ReAct iteration:
        Reason (Prompt + LLM) -> Act (Tool Selection) -> Observe (Execution & Logging).
        """
        if self.state_machine.state.active_role != self.role:
            self.state_machine.transition_role(self.role)
        messages=self.format_prompt(task)
        prompt_tokens=estimate_tokens(messages)
        completion_reserve=getattr(self.llm,"max_completion_tokens",0)
        budget_reason=self.state_machine.state.budget_limit_reason(
            prompt_tokens=prompt_tokens,
            completion_reserve=completion_reserve,
        )
        step_record=self.state_machine.begin_step(task_description=task[:500],role=self.role)
        if budget_reason:
            self.state_machine.state.context_variables["partial_result_reason"]=budget_reason
            step_record.metadata["budget_stop"]=budget_reason
            return self.state_machine.end_step(error=budget_reason,status=StepStatus.BLOCKED)
        event_bus=self.state_machine.event_bus
        provider_name=getattr(self.llm,"provider_name",None)
        model_name=getattr(self.llm,"model_name",None)
        if event_bus:
            event_bus.publish(LLMCallStartedEvent(
                session_id=self.state_machine.state.session_id,
                role=self.role,
                provider=provider_name,
                model=model_name,
                prompt_tokens=prompt_tokens,
            ))
        def publish_stream_event(stream_event: LLMStreamEvent) -> None:
            if not event_bus:
                return
            content=(
                stream_event.text
                if getattr(stream_event,"kind","")=="text"
                else json.dumps(stream_event.tool_call,ensure_ascii=False,default=str)
            )
            event_bus.publish(LLMTokenEvent(
                session_id=self.state_machine.state.session_id,
                role=self.role,
                kind=str(stream_event.kind),
                content=redact_sensitive_text(content),
            ))
        try:
            response,usage=self._invoke_llm(messages,publish_stream_event if event_bus else None)
        except Exception as exc:
            message=redact_sensitive_text(f"LLM call failed: {type(exc).__name__}: {exc}")
            if event_bus:
                event_bus.publish(LLMCallCompletedEvent(
                    session_id=self.state_machine.state.session_id,
                    role=self.role,
                    provider=provider_name,
                    model=model_name,
                    input_tokens=prompt_tokens,
                    error=message,
                ))
            step_record.metadata["llm_usage"]={"input_tokens":prompt_tokens,"output_tokens":0}
            step_record.error=message
            return self.state_machine.end_step(error=message)

        usage={key:self._redact_value(value) for key,value in usage.items()}
        step_record.metadata["llm_usage"]=usage
        state=self.state_machine.state
        state.tokens_used+=int(usage.get("total_tokens",prompt_tokens))
        call_cost=usage.get("cost_usd")
        if isinstance(call_cost,(int,float)):
            state.cost_used_usd+=float(call_cost)
        budget_reason=state.budget_limit_reason()
        if budget_reason:
            state.context_variables["partial_result_reason"]=budget_reason
        if event_bus:
            event_bus.publish(LLMCallCompletedEvent(
                session_id=self.state_machine.state.session_id,
                role=self.role,
                provider=str(usage.get("provider") or provider_name) if usage.get("provider") or provider_name else None,
                model=str(usage.get("model") or model_name) if usage.get("model") or model_name else None,
                input_tokens=int(usage.get("input_tokens",prompt_tokens)),
                output_tokens=int(usage.get("output_tokens",0)),
                cost_usd=usage.get("cost_usd"),
                latency_ms=float(usage.get("latency_ms",0.0)),
            ))

        calls=getattr(response,"tool_calls",None) or []
        if calls:
            call_data=[call if isinstance(call,dict) else call.model_dump() for call in calls]
            names=[str(call.get("name") or "") for call in call_data]
            step_record.tool_name=names[0] if len(names)==1 else "parallel_tool_calls"
            output,args_summary,succeeded=self._execute_calls(call_data)
            step_record.tool_args=self._redact_value(args_summary)
            step_record.task_description=f"Execute tool call(s): {', '.join(names)}"
            result_text=self.context_manager.store_or_truncate(output,self.role.value)
            return self.state_machine.end_step(
                tool_result=ToolResult(success=succeeded,output=result_text,error=None if succeeded else "One or more tool calls failed or were deferred.")
            )

        content=response.content if isinstance(response,AIMessage) else str(response)
        if not isinstance(content,str):
            content="\n".join(str(part.get("text","")) for part in content if isinstance(part,dict))
        intent=parse_agent_response(str(content))

        if intent.parse_error:
            return self.state_machine.end_step(error=f"Output parsing error: {intent.parse_error}. Please output valid JSON.")

        if intent.is_finished and not intent.action:
            step_record.task_description=intent.thought or "Final task completion"
            result=ToolResult.ok(output=intent.final_answer or "Task concluded.")
            return self.state_machine.end_step(tool_result=result)

        action_name=intent.action or ""
        tool=self.registry.get(action_name)
        if not tool:
            step_record.task_description=intent.thought or f"Call {action_name}"
            step_record.tool_name=action_name
            step_record.tool_args=self._redact_value(intent.action_input)
            return self.state_machine.end_step(
                error=f"Tool '{action_name}' does not exist in agent registry. Available: {self.registry.list_names()}"
            )

        step_record.task_description=intent.thought or f"Execute {action_name}"
        step_record.tool_name=action_name
        step_record.tool_args=self._redact_value(intent.action_input)
        tool_result=tool.run(intent.action_input)
        tool_result.output=self.context_manager.store_or_truncate(tool_result.output,self.role.value)
        if tool_result.error:
            tool_result.error=redact_sensitive_text(tool_result.error)
        return self.state_machine.end_step(tool_result=tool_result)

    def run_task(self,task: str,max_iterations: int=10) -> list[StepRecord]:
        """
        Run an autonomous ReAct loop up to max_iterations.
        Stops when the agent outputs a final answer or when the mission terminates.
        Detects tool-repetition stagnation and injects corrective guidance.
        """
        records: list[StepRecord] = []
        guard=LoopGuard()
        reflection: str | None=None

        for _ in range(max_iterations):
            if self.state_machine.state.is_terminal:
                break

            active_task = f"{task}\n\n{reflection}" if reflection else task

            record = self.step(active_task)
            records.append(record)

            if self.state_machine.state.context_variables.get("partial_result_reason"):
                break

            if record.tool_name is None and record.status.value == "SUCCESS":
                break

            signal=guard.observe(
                record.tool_name,
                record.tool_args,
                made_progress=record.status.value=="SUCCESS",
            )
            if signal:
                reflection=(
                    f"[REFLECTION REQUIRED] {signal.reason} Re-read the latest observation, "
                    "identify why the previous approach did not advance the task, and choose a materially different action."
                )
                ledger=self.state_machine.state.context_variables.setdefault("failure_ledger",[])
                ledger.append({"step":record.step_index,"reason":signal.reason,"tool":record.tool_name})
                self.state_machine._persist()
                if signal.should_escalate:
                    self.state_machine.state.context_variables["loop_escalation"]=(
                        "Repeated no-progress tool loop; supervisor or human review is required."
                    )
                    self.state_machine._persist()
                    break

        return records

    def run(self,task: str,max_iterations: int=10) -> str:
        """
        Run ReAct loop and return the final answer or summary of execution results.
        """
        records=self.run_task(task,max_iterations=max_iterations)
        partial_reason=self.state_machine.state.context_variables.get("partial_result_reason")
        if partial_reason:
            return f"Partial result: {partial_reason}"
        if records:
            last=records[-1]
            if last.tool_result and last.tool_result.output:
                return last.tool_result.output
            if last.error:
                return f"Execution error: {last.error}"
        return "Task completed with no output."
