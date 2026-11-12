
from pydantic import BaseModel, Field


class BenchmarkTask(BaseModel):
    id: str = Field(..., description="Unique identifier for the task")
    goal: str = Field(..., description="The mission objective provided to AegisOS")
    initial_files: dict[str, str] = Field(default_factory=dict, description="Files to write before starting (path -> content)")
    verification_script: str = Field(..., description="Test script that returns 0 on success")
    category: str | None = Field(default="feature", description="Task category: bugfix, feature, refactor")

class JudgeResult(BaseModel):
    task_id: str
    passed: bool
    pass_at_1: bool = False
    repair_cycles: int = 0
    duration_sec: float = 0.0
    total_steps: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    error_message: str | None = None
    trace: list[str] = Field(default_factory=list)

class BenchmarkReport(BaseModel):
    results: list[JudgeResult] = Field(default_factory=list)

    @property
    def total_tasks(self) -> int:
        return len(self.results)

    @property
    def passed_tasks(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def pass_rate(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return (self.passed_tasks / self.total_tasks) * 100.0
