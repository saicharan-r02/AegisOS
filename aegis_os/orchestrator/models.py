from enum import Enum
from typing import List,Optional
from pydantic import BaseModel,ConfigDict,Field
from aegis_os.agents.cto.agent import MissionPlan
from aegis_os.agents.qa.agent import TestReport
from aegis_os.agents.sec.agent import SecurityReport
from aegis_os.kernel.state import MissionStatus

class MissionPhase(str, Enum):
    """Execution lifecycle phases of a multi-department mission."""
    PLANNING="PLANNING"
    EXECUTION="EXECUTION"
    VERIFICATION="VERIFICATION"
    REPAIR="REPAIR"
    OPERATIONS="OPERATIONS"
    FINALIZATION="FINALIZATION"
    COMPLETED="COMPLETED"
    FAILED="FAILED"

class RepairCycleRecord(BaseModel):
    """
    Audit record of a closed-loop repair iteration when verification tests
    or security scans discover regressions or vulnerabilities.
    """
    model_config=ConfigDict(extra="ignore")

    cycle_index:int=Field(description="1-indexed cycle number.")
    trigger:str=Field(description="Trigger reason, e.g. QA_FAILURES, SECURITY_VULNERABILITIES, HYBRID")
    issues_detected:List[str]=Field(default_factory=list,description="List of specific failure descriptions.")
    dev_patch_summary:Optional[str]=Field(default=None,description="Summary of changes applied by AegisDev.")
    resolved:bool=Field(default=False,description="Whether this repair was verified resolved in subsequent checks.")

class MissionSummary(BaseModel):
    """
    Comprehensive final outcome and audit report for an autonomous mission.
    Captures end-to-end plan, execution traces, test/security reports, and repair cycles.
    """
    model_config=ConfigDict(extra="ignore")

    session_id:str
    goal:str
    status:MissionStatus
    plan:Optional[MissionPlan]=None
    total_steps:int=Field(default=0,ge=0)
    tasks_executed:List[str]=Field(default_factory=list)
    repair_cycles:int=Field(default=0,ge=0)
    repair_history:List[RepairCycleRecord]=Field(default_factory=list)
    qa_report:Optional[TestReport]=None
    sec_report:Optional[SecurityReport]=None
    ops_report:Optional[str]=None
    duration_seconds:float=Field(default=0.0,ge=0.0)
    error:Optional[str]=None