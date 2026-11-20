import json
import re
from pathlib import Path

from pydantic import BaseModel, Field

from aegis_os.agents.base_agent import BaseAgent, _first_json
from aegis_os.agents.cto.prompts import SYSTEM_PROMPT
from aegis_os.kernel.llm import get_llm
from aegis_os.kernel.state import AgentRole
from aegis_os.kernel.state_machine import StateMachine
from aegis_os.tools.ast_tools import ASTGrepTool
from aegis_os.tools.codebase_tools import FileOutlineTool, FindReferencesTool
from aegis_os.tools.filesystem_tools import ReadFileTool
from aegis_os.tools.git_tools import GitStatusTool
from aegis_os.tools.registry import ToolRegistry


class MissionTask(BaseModel):
    task_id: str
    title: str
    description: str
    assigned_to: str = Field(description="AegisDev | AegisQA | AegisSec | AegisOps")
    depends_on: list[str] = Field(default_factory=list)
    priority: str = Field(default="MEDIUM")
    acceptance_criteria: list[str] = Field(default_factory=list)

class MissionPlan(BaseModel):
    mission_title: str
    objective: str
    tasks: list[MissionTask]
    risk_flags: list[str] = Field(default_factory=list)

class AegisCTO(BaseAgent):
    """
    Chief Technology Officer agent.

    - Breaks a big engineering goal down into a MissionPlan.
    - Assigns each task to the right department agent.
    - Flags risks and dependencies between tasks.
    - Only gets read-only tools (no write access, by design).
    """
    def __init__(
        self,
        workspace_root: Path | None = None,
        llm_provider: str | None = None,
        llm_model: str | None = None,
        max_steps: int = 15,
        state_machine: StateMachine | None = None
    ):
        ws_root=Path(workspace_root) if workspace_root else Path.cwd()
        registry=ToolRegistry()
        registry.register(ASTGrepTool(ws_root))
        registry.register(FileOutlineTool(ws_root))
        registry.register(FindReferencesTool(ws_root))
        registry.register(GitStatusTool(ws_root))
        registry.register(ReadFileTool(ws_root))

        llm=get_llm(provider=llm_provider,model_name=llm_model,role=AgentRole.CTO,workspace_root=ws_root)

        super().__init__(name="AegisCTO",role=AgentRole.CTO,llm=llm,tools=registry,system_prompt=SYSTEM_PROMPT,max_steps=max_steps,state_machine=state_machine)
        self.workspace_root=ws_root

    def plan_mission(self,goal: str) -> MissionPlan:
        """
        Turn a goal into a MissionPlan.

        First runs the normal ReAct session and tries to parse its output.
        Some reasoning models talk before they give JSON, so if parsing
        fails we retry twice with stricter prompts.
        """
        prompt = (
            "Please analyze the following engineering goal and produce a structured "
            "Keep the plan compact (1-2 tasks max for focused bug fixes; combine code fix and test update into one task when in the same repo). "
            "MissionPlan JSON as specified in your system prompt.\n\n"
            f"## Goal\n{goal}"
        )
        raw_output=self.run(prompt, max_iterations=8)
        try:
            return self._parse_mission_plan(raw_output)
        except ValueError:
            pass
        followup=(
            "You have completed your analysis. Now output ONLY the MissionPlan as a "
            "single valid JSON object. The JSON must start with { and end with }. "
            "Include fields: mission_title, objective, tasks (list), risk_flags (list). "
            "Each task must have: task_id, title, description, assigned_to, depends_on, "
            "priority, acceptance_criteria. NO other text.\n\n"
            f"Goal: {goal}"
        )
        reply_text=self.run(followup, max_iterations=2)
        try:
            return self._parse_mission_plan(reply_text)
        except ValueError:
            pass
        minimal_prompt=(
            f"Output ONLY valid JSON for this goal. No reasoning, no markdown. Start with {{.\n"
            f"Goal: {goal}\n"
            "Schema: " + json.dumps({
                "mission_title": "<short title for THIS goal>",
                "objective": "<one sentence>",
                "tasks": [{
                    "task_id": "T001",
                    "title": "<task title>",
                    "description": "<what to do>",
                    "assigned_to": "AegisDev",
                    "depends_on": [],
                    "priority": "HIGH",
                    "acceptance_criteria": ["<verifiable condition>"],
                }],
                "risk_flags": [],
            })
        )
        reply_text=self.run(minimal_prompt, max_iterations=2)
        try:
            return self._parse_mission_plan(reply_text)
        except ValueError:
            from langchain_core.messages import HumanMessage, SystemMessage
            res = self.llm.complete([
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=minimal_prompt),
            ])
            return self._parse_mission_plan(self._reply_text(res.message))

    @staticmethod
    def _reply_text(response) -> str:
        return str(getattr(response, "content", str(response)))

    def _parse_mission_plan(self, raw: str) -> MissionPlan:
        """
        Find a MissionPlan JSON in the agent's output and validate it.

        Looks in ```json fenced blocks first, then scans the whole text for
        any '{' that starts a JSON object containing "tasks". raw_decode lets
        us ignore whatever text comes after the JSON.
        """
        for match in re.finditer(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL):
            candidate = match.group(1).strip()
            if not candidate.startswith("{"):
                continue
            try:
                data=_first_json(candidate)
                if "tasks" in data:
                    return MissionPlan.model_validate(data)
            except Exception:
                continue
        decoder=json.JSONDecoder()
        text=raw.strip()
        for pos,char in enumerate(text):
            if char!="{":
                continue
            try:
                obj,_=decoder.raw_decode(text,pos)
                if isinstance(obj,dict) and "tasks" in obj:
                    return MissionPlan.model_validate(obj)
            except Exception:
                continue

        raise ValueError(
            "AegisCTO produced no parseable MissionPlan JSON.\n"
            f"Raw output:\n{raw[:500]}..."
        )
