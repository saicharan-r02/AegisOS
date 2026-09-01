import os
import subprocess
import time
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class ExecutionResult(BaseModel):
    """Result of running a command inside the AegisOS sandbox."""
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool =False

    @property
    def is_success(self)->bool:
        return self.exit_code==0 and not self.timed_out

class SandboxExecutor:
    """
    Executes shell commands safely within an isolated workspace directory.
    Guarantees timeout protection and clean output capture.
    """
    def __init__(self,workspace_root: Optional[str]=None, default_timeout: int =30):
        self.workspace_root=Path(workspace_root or os.getcwd()).resolve()
        self.default_timeout=default_timeout

    def run_command(self,command: str,timeout: Optional[int]=None,env_vars: Optional[Dict[str,str]]=None)->ExecutionResult:
        timeout_limit=timeout or self.default_timeout
        start_time=time.time()

        # Build clean environment
        env=os.environ.copy()
        if env_vars:
            env.update(env_vars)

        try:
            process=subprocess.Popen(
                command,
                shell=True,
                cwd=str(self.workspace_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env)

            stdout,stderr=process.communicate(timeout=timeout_limit)
            duration=time.time()-start_time

            return ExecutionResult(
                command=command,
                exit_code=process.returncode,
                stdout=stdout.strip(),
                stderr=stderr.strip(),
                duration_seconds=round(duration,3),
                timed_out=False)

        except subprocess.TimeoutExpired:
            process.kill()
            stdout,stderr=process.communicate()
            duration=time.time()-start_time
            return ExecutionResult(
                command=command,
                exit_code=-1,
                stdout=stdout.strip(),
                stderr=f"Command timed out after {timeout_limit} seconds.",
                duration_seconds=round(duration,3),
                timed_out=True)
        except Exception as e:
            duration=time.time()-start_time
            return ExecutionResult(
                command=command,
                exit_code=-1,
                stdout="",
                stderr=f"Execution error:{str(e)}",
                duration_seconds=round(duration,3),
                timed_out=False)