from typing import List,Dict,Any,Optional
from pydantic import BaseModel,Field
from datetime import datetime


class StepRecord(BaseModel):
    """Records an individual thought -> action -> observation step."""
    step_number: int
    thought: str
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_output: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class AgentState(BaseModel):
    """Global execution state and working memory for AegisOS agents."""
    task_id: str
    goal: str
    max_steps: int =15
    current_step: int =0
    is_completed: bool =False
    final_response: Optional[str] =None
    error: Optional[str] =None
    
    # History & Memory
    steps: List[StepRecord] =Field(default_factory=list)
    files_inspected: List[str] =Field(default_factory=list)
    files_modified: List[str] =Field(default_factory=list)
    
    def add_step(
        self,
        thought: str,
        tool_name: Optional[str] =None,
        tool_input: Optional[Dict[str,Any]] =None,
        tool_output: Optional[str] =None
    ) -> StepRecord:
        self.current_step+=1
        record=StepRecord(
            step_number=self.current_step,
            thought=thought,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output
        )
        self.steps.append(record)
        return record

    def get_history_summary(self) -> str:
        """Formats the step history for LLM context prompting."""
        if not self.steps:
            return "No previous steps taken yet."
        
        history=[]
        for step in self.steps:
            h=f"Step {step.step_number}:\nThought: {step.thought}"
            if step.tool_name:
                h+=f"\nAction: Called tool '{step.tool_name}' with args {step.tool_input}"
                h+=f"\nObservation: {step.tool_output}"
            history.append(h)
        return "\n\n".join(history)