import json
import uuid
from typing import List,Dict,Any,Optional
from langchain_core.messages import SystemMessage, HumanMessage

from Aegis_OS.kernel.llm import get_llm
from Aegis_OS.kernel.state import AgentState
from Aegis_OS.tools.base import BaseAegisTool
from Aegis_OS.tools.filesystem_tools import (
    ReadFileTool,
    WriteFileTool,
    ListDirTool,
    SearchCodeTool
)
from Aegis_OS.tools.git_tools import GitDiffTool,GitStatusTool


DEV_SYSTEM_PROMPT="""You are AegisDev, an elite Autonomous Software Engineering Agent in AegisOS.
Your objective is to solve software engineering tasks, inspect codebases, investigate bugs, and write clean, verified fixes.

You operate in a continuous Reason -> Act -> Observe loop:
1. Reason about the current goal and past observations.
2. Select an appropriate tool to inspect or modify the code.
3. If you have achieved the goal completely, output your final response.

CRITICAL RULES:
- Always read a file before modifying it.
- Never guess line numbers or function contents; use read_file or search_code.
- Keep your fixes minimal and targeted.
- When done, explain what was fixed and provide evidence.
"""


class AegisDevAgent:
    """Autonomous Software Engineering Agent."""

    def __init__(self, tools: Optional[List[BaseAegisTool]] = None,model_name: Optional[str] =None):
        # Default tools for AegisDev
        default_tools=[
            ReadFileTool(),
            WriteFileTool(),
            ListDirTool(),
            SearchCodeTool(),
            GitDiffTool(),
            GitStatusTool()
        ]
        self.tools: Dict[str,BaseAegisTool]={
            t.name: t for t in (tools or default_tools)}
        
        # Bind tools to LLM
        self.llm=get_llm(model_name=model_name)
        langchain_tools=[t.to_langchain_tool() for t in self.tools.values()]
        self.llm_with_tools=self.llm.bind_tools(langchain_tools)

    def run(self,goal: str,max_steps: int =10)-> AgentState:
        """Executes the autonomous loop until completion or step exhaustion."""
        state=AgentState(task_id=str(uuid.uuid4())[:8],goal=goal,max_steps=max_steps)

        while state.current_step<state.max_steps and not state.is_completed:
            # Build conversation history
            messages=[
                SystemMessage(content=DEV_SYSTEM_PROMPT),
                HumanMessage(content=f"GOAL: {state.goal}\n\nHISTORY SO FAR:\n{state.get_history_summary()}\n\nWhat is your next action?")
            ]

            try:
                response=self.llm_with_tools.invoke(messages)
            except Exception as e:
                state.error=f"LLM invocation failed: {str(e)}"
                break

            # 1. Check if LLM decided to call any tools
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    tool_name=tool_call["name"]
                    tool_args=tool_call["args"]
                    thought=response.content or f"Calling tool {tool_name}"

                    if tool_name in self.tools:
                        tool_result=self.tools[tool_name].execute(**tool_args)
                        output_str=tool_result.to_agent_string()

                        if tool_name=="read_file":
                            state.files_inspected.append(tool_args.get("file_path",""))
                        elif tool_name=="write_file":
                            state.files_modified.append(tool_args.get("file_path",""))

                        state.add_step(
                            thought=str(thought),
                            tool_name=tool_name,
                            tool_input=tool_args,
                            tool_output=output_str
                        )
                    else:
                        state.add_step(
                            thought=str(thought),
                            tool_name=tool_name,
                            tool_input=tool_args,
                            tool_output=f"Error: Unknown tool '{tool_name}'"
                        )
            else:
                # LLM finished task without needing further tools
                thought=response.content or "Completed task."
                state.add_step(thought=thought)
                state.is_completed=True
                state.final_response=str(response.content)
                break

        if not state.is_completed and state.current_step>=state.max_steps:
            state.error=f"Exceeded maximum step limit ({state.max_steps})."

        return state