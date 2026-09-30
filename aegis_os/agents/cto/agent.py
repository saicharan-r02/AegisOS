import json
import re
from pathlib import Path
from typing import Any,Dict,List,Optional
from langchain_core.messages import HumanMessage,SystemMessage
from pydantic import BaseModel,Field
from aegis_os.agents.base_agent import BaseAgent, _first_json
from aegis_os.agents.cto.prompts import SYSTEM_PROMPT
from aegis_os.kernel.llm import get_llm
from aegis_os.kernel.state import AgentRole
from aegis_os.kernel.state_machine import StateMachine
from aegis_os.tools.ast_tools import ASTGrepTool
from aegis_os.tools.filesystem_tools import ReadFileTool
from aegis_os.tools.git_tools import GitStatusTool
from aegis_os.tools.registry import ToolRegistry

class MissionTask(BaseModel):
    """A single atomic task assigned to an engineering department."""
    task_id: str
    title: str
    description: str
    assigned_to: str = Field(description="AegisDev | AegisQA | AegisSec | AegisOps")
    depends_on: List[str] = Field(default_factory=list)
    priority: str = Field(default="MEDIUM")
    acceptance_criteria: List[str] = Field(default_factory=list)

class MissionPlan(BaseModel):
    """Structured engineering plan produced by AegisCTO."""
    mission_title: str
    objective: str
    tasks: List[MissionTask]
    risk_flags: List[str] = Field(default_factory=list)

class AegisCTO(BaseAgent):
    """
    Chief Technology Officer Agent.
    Responsibilities:
    - Decomposes complex engineering goals into a structured MissionPlan.
    - Assigns each task to the appropriate department agent.
    - Identifies risk flags and dependencies between tasks.
    - Only uses READ-ONLY tools: ast_grep, git_status, read_file.
    RBAC: Write tools are intentionally excluded.
    """

    def __init__(self,workspace_root: Optional[Path] = None,llm_provider: str = "openai",llm_model: Optional[str] = None,max_steps: int = 15,state_machine: Optional[StateMachine] = None):
        ws_root=Path(workspace_root) if workspace_root else Path.cwd()
        registry=ToolRegistry()
        # CTO is intentionally restricted to read-only tools for reconnaissance and planning.
        registry.register(ASTGrepTool())
        registry.register(GitStatusTool())
        registry.register(ReadFileTool(ws_root))

        llm=get_llm(provider=llm_provider,model_name=llm_model)

        super().__init__(
            name="AegisCTO",
            role=AgentRole.CTO,
            llm=llm,
            tools=registry,
            system_prompt=SYSTEM_PROMPT,
            max_steps=max_steps,
            state_machine=state_machine,
        )
        self.workspace_root=ws_root

    def plan_mission(self,goal: str) -> MissionPlan:
        """
        Run a full ReAct session to decompose the goal, then parse the
        final JSON MissionPlan from the agent's output.
        Supports chain-of-thought models that output reasoning before JSON.
        Falls back through two progressively more explicit prompts.
        """
        prompt=(
            f"Please analyze the following engineering goal and produce a structured "
            f"MissionPlan JSON as specified in your system prompt.\n\n"
            f"## Goal\n{goal}"
        )
        raw_output=self.run(prompt)

        try:
            return self._parse_mission_plan(raw_output)
        except ValueError:
            pass

        # Fallback 1: dedicated follow-up forcing raw JSON
        followup=(
            "You have completed your analysis. Now output ONLY the MissionPlan as a "
            "single valid JSON object. The JSON must start with { and end with }. "
            "Include fields: mission_title, objective, tasks (list), risk_flags (list). "
            "Each task must have: task_id, title, description, assigned_to, depends_on, "
            "priority, acceptance_criteria. NO other text.\n\n"
            f"Goal: {goal}"
        )
        messages=[
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=followup),
        ]
        response=self.llm.invoke(messages)
        content=getattr(response,"content",str(response))
        try:
            return self._parse_mission_plan(str(content))
        except ValueError:
            pass

        # Fallback 2: minimal single-shot with strict schema
        minimal_prompt=(
            f"Output ONLY valid JSON for goal '{goal}'. No reasoning, no markdown. Start with {{:\n"
            '{"mission_title":"Calculator","objective":"Build calculator","tasks":['
            '{"task_id":"T001","title":"Implement","description":"Write calculator.py",'
            '"assigned_to":"AegisDev","depends_on":[],"priority":"HIGH","acceptance_criteria":["passes tests"]}],'
            '"risk_flags":["division by zero"]}'
        )
        messages2=[HumanMessage(content=minimal_prompt)]
        response2=self.llm.invoke(messages2)
        content2=getattr(response2,"content",str(response2))
        return self._parse_mission_plan(str(content2))

    def _parse_mission_plan(self,raw: str) -> MissionPlan:
        """Extract and validate the MissionPlan JSON from agent output.
        Handles ```json blocks, inline JSON, and deeply-nested JSON in reasoning text.
        Uses raw_decode so trailing data after the JSON is safely ignored.
        """
        # 1. Try all ```json ... ``` or ``` ... ``` code blocks
        for block_match in re.finditer(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL):
            candidate=block_match.group(1).strip()
            if candidate.startswith("{"):
                try:
                    data=_first_json(candidate)
                    if "tasks" in data:
                        return MissionPlan.model_validate(data)
                except (json.JSONDecodeError, ValueError, Exception):
                    continue

        # 2. Scan for any JSON object containing 'tasks' key anywhere in the text
        decoder=json.JSONDecoder()
        stripped=raw.strip()
        for i, ch in enumerate(stripped):
            if ch == '{':
                try:
                    obj, _ = decoder.raw_decode(stripped, i)
                    if isinstance(obj, dict) and "tasks" in obj:
                        return MissionPlan.model_validate(obj)
                except (json.JSONDecodeError, ValueError, Exception):
                    continue

        raise ValueError(
            f"AegisCTO produced no parseable MissionPlan JSON.\n"
            f"Raw output:\n{raw[:500]}..."
        )
