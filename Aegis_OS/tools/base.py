from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """Standardized output returned by every AegisOS tool."""
    success: bool
    output: Optional[Any]=None
    error: Optional[str]=None
    metadata: Dict[str,Any]=Field(default_factory=dict)

    def to_agent_string(self)->str:
        """Converts the result into a clean format for LLM context."""
        if self.success:
            return str(self.output)
        return f"TOOL ERROR: {self.error}"


class BaseAegisTool(ABC):
    """Abstract Base Class for all AegisOS tools."""
    name: str
    description: str
    args_schema: Type[BaseModel]

    @abstractmethod
    def _run(self,**kwargs)->ToolResult:
        """Core execution logic to be implemented by child tools."""
        pass

    def execute(self,**kwargs)->ToolResult:
        """
        Public execution wrapper:
        1. Validates input arguments using args_schema.
        2. Executes _run() safely.
        3. Catches and formats any unhandled exceptions into ToolResult.
        """
        try:
            # Validate input arguments against Pydantic schema
            validated_args=self.args_schema(**kwargs)
            return self._run(**validated_args.model_dump())
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Execution error in tool '{self.name}': {str(e)}",
                metadata={"tool_name": self.name}
            )

    def to_langchain_tool(self):
        """
        Allows our tool to be bound directly to LangChain / LangGraph 
        or other standard tool-calling LLMs.
        """
        from langchain_core.tools import StructuredTool
        return StructuredTool.from_function(
            func=self.execute,
            name=self.name,
            description=self.description,
            args_schema=self.args_schema,
            return_direct=False)