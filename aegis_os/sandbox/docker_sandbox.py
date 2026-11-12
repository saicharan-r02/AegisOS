"""Docker execution backend with a restricted, network-isolated container."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from aegis_os.sandbox.base import CommandResult, SandboxExecutor
from aegis_os.sandbox.path_guard import PathTraversalError, validate_path
from aegis_os.sandbox.policy import CommandPolicy, CommandTier
from aegis_os.sandbox.quotas import ExecutionQuota

_IGNORED_NAMES = {
    ".git",
    ".aegis",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".tox",
    ".ssh",
    ".aws",
    ".azure",
    ".gcloud",
    ".kube",
    "credentials",
    "secrets",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
}


class DockerSandbox(SandboxExecutor):
    """Run approved commands inside a non-root, network-off Docker container.

    The workspace is copied into a temporary read-only snapshot. Sensitive
    paths, symlinks, Git internals, and caches are omitted from that snapshot.
    Agent edits remain the responsibility of path-guarded file tools.
    """

    def __init__(
        self,
        workspace_root: Path,
        image: str = "aegis-sandbox-python:latest",
        *,
        cpu_limit: float = 1.0,
        memory_limit: str = "1g",
        pid_limit: int = 128,
        network_allowlist: tuple[str, ...] = (),
        policy: CommandPolicy | None = None,
        docker_executable: str = "docker",
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.image = image
        self.cpu_limit = cpu_limit
        self.memory_limit = memory_limit
        self.pid_limit = pid_limit
        self.network_allowlist = network_allowlist
        self.policy = policy or CommandPolicy()
        self.docker_executable = docker_executable

    def execute_command(
        self,
        command: str,
        cwd: Path | None = None,
        quota: ExecutionQuota | None = None,
    ) -> CommandResult:
        active_quota = quota or ExecutionQuota()
        decision = self.policy.evaluate(command, self.workspace_root)
        if decision.tier != CommandTier.AUTO_ALLOW:
            return CommandResult(
                exit_code=126,
                stdout="",
                stderr=f"Command policy {decision.tier.value}: {decision.reason}",
            )
        if self.network_allowlist:
            return CommandResult(
                exit_code=126,
                stdout="",
                stderr=(
                    "Network allow-list was requested but no filtered egress proxy is configured. "
                    "Network access remains disabled."
                ),
            )
        docker_path = shutil.which(self.docker_executable)
        if docker_path is None:
            return CommandResult(
                exit_code=127, stdout="", stderr="Docker CLI is not installed or not on PATH."
            )
        try:
            cwd_path = validate_path(cwd or self.workspace_root, self.workspace_root)
        except (PathTraversalError, ValueError) as exc:
            return CommandResult(exit_code=126, stdout="", stderr=str(exc))

        try:
            argv = list(decision.argv) or shlex.split(command, posix=os.name != "nt")
        except ValueError as exc:
            return CommandResult(exit_code=126, stdout="", stderr=f"Unable to parse command: {exc}")
        if not argv:
            return CommandResult(exit_code=126, stdout="", stderr="Empty command.")

        try:
            with tempfile.TemporaryDirectory(prefix="aegis-sandbox-") as temp_name:
                snapshot = Path(temp_name) / "workspace"
                self._copy_workspace(snapshot)
                relative_cwd = cwd_path.relative_to(self.workspace_root)
                container_cwd = Path("/workspace") / relative_cwd.as_posix()
                container_name = f"aegis-{uuid.uuid4().hex[:20]}"
                docker_command = [
                    docker_path,
                    "run",
                    "--rm",
                    "--name",
                    container_name,
                    "--network",
                    "none",
                    "--read-only",
                    "--cpus",
                    str(self.cpu_limit),
                    "--memory",
                    self.memory_limit,
                    "--pids-limit",
                    str(self.pid_limit),
                    "--user",
                    "1000:1000",
                    "--security-opt",
                    "no-new-privileges:true",
                    "--cap-drop",
                    "ALL",
                    "--tmpfs",
                    "/tmp:rw,noexec,nosuid,size=256m",
                    "--mount",
                    f"type=bind,src={snapshot},dst=/workspace,readonly",
                    "--workdir",
                    container_cwd.as_posix(),
                    "--env",
                    "HOME=/tmp",
                    "--env",
                    "PYTHONDONTWRITEBYTECODE=1",
                    "--env",
                    "PYTEST_ADDOPTS=-p no:cacheprovider",
                    self.image,
                    *argv,
                ]
                try:
                    result = subprocess.run(
                        docker_command,
                        capture_output=True,
                        text=True,
                        timeout=active_quota.timeout_seconds,
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    subprocess.run(
                        [docker_path, "kill", container_name],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=False,
                    )
                    return CommandResult(
                        exit_code=124,
                        stdout="",
                        stderr=f"Docker command exceeded {active_quota.timeout_seconds} seconds and was killed.",
                        timed_out=True,
                    )
                stdout, stdout_truncated = self._truncate(
                    result.stdout, active_quota.max_output_bytes // 2
                )
                stderr, stderr_truncated = self._truncate(
                    result.stderr, active_quota.max_output_bytes // 2
                )
                return CommandResult(
                    exit_code=result.returncode,
                    stdout=stdout,
                    stderr=stderr,
                    output_truncated=stdout_truncated or stderr_truncated,
                )
        except OSError as exc:
            return CommandResult(exit_code=127, stdout="", stderr=f"Docker execution failed: {exc}")

    def _copy_workspace(self, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        for source in self.workspace_root.iterdir():
            self._copy_entry(source, destination / source.name)

    def _copy_entry(self, source: Path, destination: Path) -> None:
        folded = source.name.casefold().rstrip(" .")
        if (
            folded in _IGNORED_NAMES
            or folded.startswith(".env")
            or folded.startswith("credentials.")
            or folded.startswith("secrets.")
            or source.is_symlink()
        ):
            return
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            for child in source.iterdir():
                self._copy_entry(child, destination / child.name)
        elif source.is_file() and source.suffix.lower() not in {
            ".pem",
            ".key",
            ".p12",
            ".pfx",
            ".ppk",
        }:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)

    @staticmethod
    def _truncate(text: str, max_bytes: int) -> tuple[str, bool]:
        encoded = text.encode("utf-8", errors="replace")
        if len(encoded) <= max_bytes:
            return text, False
        clipped = encoded[:max_bytes].decode("utf-8", errors="replace")
        return clipped + "\n[Docker output truncated by AegisOS.]", True
