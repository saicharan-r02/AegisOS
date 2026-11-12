"""Diagnostic doctor command checking environment, keys, Docker, git, models, and permissions."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from aegis_os.cli.display import AegisDisplay
from aegis_os.config.validator import validate_config_file


class AegisDoctor:
    """Performs comprehensive pre-flight health checks for AegisOS."""

    def __init__(self, workspace_root: Path | str = ".") -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.display = AegisDisplay()

    def run_diagnostics(self) -> int:
        """Run all diagnostic checks and print report. Returns 0 if healthy, 1 if critical issue found."""
        self.display.console.print(
            "\n[bold cyan]╔═══════════════════════════════════════════════════════════╗[/bold cyan]"
        )
        self.display.console.print(
            "[bold cyan]║[/bold cyan]   [bold white]AegisOS System Health & Diagnostics (Doctor v2.0)[/bold white]       [bold cyan]║[/bold cyan]"
        )
        self.display.console.print(
            "[bold cyan]╚═══════════════════════════════════════════════════════════╝[/bold cyan]\n"
        )

        all_ok = True

        # 1. Python Version
        py_ver = sys.version_info
        if py_ver >= (3, 11):
            self.display.console.print(
                f"[bold green]✔ Python Version:[/bold green] {sys.version.split()[0]} (supported >= 3.11)"
            )
        else:
            self.display.console.print(
                f"[bold red]✘ Python Version:[/bold red] {sys.version.split()[0]} (requires >= 3.11)"
            )
            all_ok = False

        # 2. Git Installation & Workspace Status
        git_path = shutil.which("git")
        if git_path:
            git_ver = subprocess.run(
                ["git", "--version"], capture_output=True, text=True, check=False
            )
            self.display.console.print(
                f"[bold green]✔ Git Client:[/bold green] {git_ver.stdout.strip()}"
            )
            # Check if workspace is a git repo
            is_git_repo = (self.workspace_root / ".git").exists()
            if is_git_repo:
                self.display.console.print(
                    f"[bold green]✔ Git Workspace:[/bold green] Active repository at {self.workspace_root}"
                )
            else:
                self.display.console.print(
                    f"[yellow]⚠ Git Workspace:[/yellow] {self.workspace_root} is not a git repository (snapshot fallback enabled)"
                )
        else:
            self.display.console.print(
                "[bold red]✘ Git Client:[/bold red] git executable not found on PATH"
            )
            all_ok = False

        # 3. Docker Daemon Availability
        docker_path = shutil.which("docker")
        if docker_path:
            docker_info = subprocess.run(
                ["docker", "info"], capture_output=True, text=True, check=False
            )
            if docker_info.returncode == 0:
                self.display.console.print(
                    "[bold green]✔ Docker Daemon:[/bold green] Running and accessible"
                )
            else:
                self.display.console.print(
                    "[yellow]⚠ Docker Daemon:[/yellow] Docker binary found but daemon is not responding (falling back to --unsafe-local)"
                )
        else:
            self.display.console.print(
                "[yellow]⚠ Docker Daemon:[/yellow] Not installed (commands will run in host subprocess mode under --unsafe-local)"
            )

        # 4. LLM API Key Presence
        from aegis_os.kernel.llm import LLMConfig

        cfg = LLMConfig()
        providers = {
            "NVIDIA NIM": os.getenv("NVIDIA_API_KEY") or cfg.nvidia_api_key,
        }
        active_keys = [name for name, key in providers.items() if key]
        if active_keys:
            self.display.console.print(
                f"[bold green]✔ LLM API Keys:[/bold green] Configured: {', '.join(active_keys)}"
            )
        else:
            self.display.console.print(
                "[yellow]⚠ LLM API Keys:[/yellow] No API keys detected in environment (offline/mock mode only)"
            )

        # 5. Configuration Validation
        config_path = self.workspace_root / "aegis.toml"
        if not config_path.exists():
            config_path = Path("aegis.toml")
        if config_path.exists():
            valid, msgs = validate_config_file(config_path)
            if valid:
                self.display.console.print(
                    f"[bold green]✔ Configuration:[/bold green] '{config_path}' valid"
                )
            else:
                self.display.console.print(
                    f"[bold red]✘ Configuration:[/bold red] '{config_path}' invalid: {msgs}"
                )
                all_ok = False
        else:
            self.display.console.print(
                "[yellow]⚠ Configuration:[/yellow] aegis.toml not found; using built-in defaults"
            )

        # 6. Workspace Filesystem Permissions
        try:
            test_file = self.workspace_root / ".aegis_doctor_write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            self.display.console.print(
                f"[bold green]✔ Filesystem Permissions:[/bold green] Read/Write confirmed on {self.workspace_root}"
            )
        except Exception as exc:
            self.display.console.print(
                f"[bold red]✘ Filesystem Permissions:[/bold red] Cannot write to workspace: {exc}"
            )
            all_ok = False

        self.display.console.print("\n" + ("=" * 60))
        if all_ok:
            self.display.console.print(
                "[bold green]✔ All critical system invariants satisfied. Ready for mission execution.[/bold green]\n"
            )
            return 0
        else:
            self.display.console.print(
                "[bold red]✘ One or more critical checks failed. Resolve issues above.[/bold red]\n"
            )
            return 1
