import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from aegis_os.agents.base_agent import BaseAgent
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
    assigned_to: str =Field(description="AegisDev | AegisQA | AegisSec | AegisOps")
    depends_on: List[str] =Field(default_factory=list)
    priority: str = Field(default="MEDIUM")
    acceptance_criteria: List[str] =Field(default_factory=list)

class MissionPlan(BaseModel):
    """Structured engineering plan produced by AegisCTO."""
    mission_title: str
    objective: str
    tasks: List[MissionTask]
    risk_flags: List[str]=Field(default_factory=list)

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
        #CTO is READ-ONLY — reconnaissance and analysis only
        registry.register(ASTGrepTool())
        registry.register(GitStatusTool())
        registry.register(ReadFileTool(ws_root))

        llm=get_llm(provider=llm_provider,model_name=llm_model or "gpt-4o")

        super().__init__(
            name="AegisCTO",
            role=AgentRole.CTO,
            llm=llm,
            tools=registry,
            system_prompt=SYSTEM_PROMPT,
            max_steps=max_steps,
            state_machine=state_machine,
        )
        self.workspace_root = ws_root

    def plan_mission(self,goal: str) -> MissionPlan:
        """
        Run a full ReAct session to decompose the goal, then parse the
        final JSON MissionPlan from the agent's output.
        Args:
            goal: High-level engineering objective as plain text.
        Returns:
            A validated MissionPlan Pydantic model.
        Raises:
            ValueError: If the agent output cannot be parsed into a valid MissionPlan.
        """
        prompt=(
            f"Please analyze the following engineering goal and produce a structured "
            f"MissionPlan JSON as specified in your system prompt.\n\n"
            f"## Goal\n{goal}"
        )
        raw_output=self.run(prompt)
        return self._parse_mission_plan(raw_output)

    def _parse_mission_plan(self,raw: str) -> MissionPlan:
        """Extract and validate the MissionPlan JSON from agent output."""
        #Try to extract from a markdown JSON code block first
        block_match=re.search(r"```json\s*(.*?)\s*```",raw,re.DOTALL)
        if block_match:
            json_str=block_match.group(1)
        else:
            #Fallback:try to find a raw JSON object
            brace_match=re.search(r"\{.*\}",raw,re.DOTALL)
            if brace_match:
                json_str=brace_match.group(0)
            else:
                raise ValueError(
                    f"AegisCTO produced no parseable MissionPlan JSON.\n"
                    f"Raw output:\n{raw}"
                )

        try:
            data:Dict[str,Any]=json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"AegisCTO output is not valid JSON: {exc}\nRaw:\n{json_str}"
            ) from exc

        return MissionPlan.model_validate(data)