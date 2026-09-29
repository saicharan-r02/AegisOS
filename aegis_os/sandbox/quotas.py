from pydantic import BaseModel,ConfigDict,Field

class ExecutionQuota(BaseModel):
    """
    Hard execution resource limits.
    If timeout_seconds is exceeded, the process tree is forcefully terminated.
    If max_output_bytes is exceeded, stdout/stderr are truncated with a warning
    rather than crashing the caller or flooding memory.
    """
    model_config=ConfigDict(frozen=True)
    
    timeout_seconds:float=Field(default=30.0,gt=0,description="Wall-clock seconds before process tree is killed.")
    
    max_output_bytes:int=Field(default=100_000,gt=0,description="Maximum total bytes captured from stdout + stderr combined.")