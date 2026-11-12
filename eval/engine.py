import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from aegis_os.kernel.checkpoint import CheckpointStore
from aegis_os.kernel.context import redact_sensitive_text
from aegis_os.kernel.events import EventBus
from aegis_os.kernel.state_machine import MissionOrchestrator
from aegis_os.sandbox.docker_sandbox import DockerSandbox
from aegis_os.sandbox.quotas import ExecutionQuota
from aegis_os.sandbox.subprocess_sandbox import SubprocessSandbox
from eval.models import BenchmarkTask, JudgeResult


class AegisJudge:
    def __init__(self, provider: str | None = None, model: str | None = None, max_repairs: int = 3, max_steps: int = 50, unsafe_local: bool = False):
        self.provider = provider
        self.model = model
        self.max_repairs = max_repairs
        self.max_steps = max_steps
        self.unsafe_local=unsafe_local

    def run_task(self, task: BenchmarkTask) -> JudgeResult:
        with tempfile.TemporaryDirectory() as temp_dir:
            ws_path = Path(temp_dir).resolve()

            for rel_path, content in task.initial_files.items():
                file_path = ws_path / rel_path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")

            subprocess.run(["git", "init"], cwd=ws_path, capture_output=True, check=True)
            subprocess.run(["git", "config", "user.name", "AegisOS Benchmark"], cwd=ws_path, capture_output=True, check=True)
            subprocess.run(["git", "config", "user.email", "benchmark@aegisos.ai"], cwd=ws_path, capture_output=True, check=True)

            start_time = time.time()

            db_path = ws_path / ".aegis" / "checkpoints.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            store = CheckpointStore(db_path=db_path)
            bus = EventBus()

            orchestrator = MissionOrchestrator(
                workspace_root=ws_path,
                llm_provider=self.provider,
                llm_model=self.model,
                checkpoint_store=store,
                event_bus=bus,
                max_repair_cycles=self.max_repairs,
                max_steps=self.max_steps,
                unsafe_local=self.unsafe_local,
            )

            summary = orchestrator.execute_mission(task.goal)
            duration_sec = time.time() - start_time

            # Count steps and preserve a redacted, compact diagnostic trace.
            step_records=store.list_steps(summary.session_id) if summary.session_id else []
            total_steps=len(step_records)
            trace=[]
            for step in step_records:
                item=(
                    f"{step.step_index} {step.role.value} {step.status.value} "
                    f"tool={step.tool_name or '-'} task={step.task_description[:160]}"
                )
                if step.error:
                    item+=f" error={redact_sensitive_text(step.error)[:240]}"
                if step.tool_result and step.tool_result.output:
                    item+=f" output={redact_sensitive_text(step.tool_result.output)[:240]}"
                trace.append(item)

            verification_script_path = ws_path / "verify.py"
            verification_script_path.write_text(task.verification_script, encoding="utf-8")

            try:
                verifier_sandbox=(SubprocessSandbox() if self.unsafe_local else DockerSandbox(ws_path))
                verification_command=(
                    subprocess.list2cmdline([sys.executable,"verify.py"])
                    if self.unsafe_local and os.name=="nt"
                    else shlex.join([sys.executable,"verify.py"])
                    if self.unsafe_local
                    else "python verify.py"
                )
                result=verifier_sandbox.execute_command(
                    verification_command,
                    cwd=ws_path,
                    quota=ExecutionQuota(timeout_seconds=10),
                )
                passed=result.success
                verification_output="\n".join(
                    part.strip() for part in (result.stdout,result.stderr) if part and part.strip()
                )
                error_parts=[]
                if not passed:
                    error_parts.append(f"Verifier exited with code {result.exit_code}.")
                    if verification_output:
                        error_parts.append(verification_output)
                if summary.error:
                    error_parts.append(f"Mission error: {summary.error}")
                error_message="\n".join(error_parts) or None
            except Exception as e:
                passed = False
                error_message = str(e)

            store.close()

            return JudgeResult(
                task_id=task.id,
                passed=passed,
                pass_at_1=passed and len(summary.repair_history) == 0,
                repair_cycles=len(summary.repair_history),
                duration_sec=duration_sec,
                total_steps=total_steps,
                total_tokens=summary.tokens_used,
                cost_usd=summary.cost_used_usd,
                error_message=error_message,
                trace=trace,
            )
