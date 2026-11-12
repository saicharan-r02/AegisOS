"""In-code command tiers for the agent's command execution tools."""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from aegis_os.sandbox.path_guard import PathTraversalError, validate_path


class CommandTier(str, Enum):
    AUTO_ALLOW = "auto_allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyDecision:
    tier: CommandTier
    reason: str
    argv: tuple[str, ...] = ()


class CommandPolicy:
    """Classify commands before any process or container is started."""

    _DENIED_EXECUTABLES = {
        "sudo",
        "su",
        "doas",
        "runas",
        "diskpart",
        "format",
        "mkfs",
        "fdisk",
        "shutdown",
        "reboot",
        "reg",
        "mount",
        "umount",
        "powershell",
        "pwsh",
        "cmd.exe",
        "cmd",
        "docker",
        "podman",
        "systemctl",
        "sc.exe",
    }
    _APPROVAL_EXECUTABLES = {
        "curl",
        "wget",
        "ssh",
        "scp",
        "nc",
        "netcat",
        "pip",
        "pip3",
        "uv",
        "npm",
        "npx",
        "yarn",
        "pnpm",
        "cargo",
        "git",
    }
    _DELETE_EXECUTABLES = {"rm", "rmdir", "del", "erase", "unlink", "remove-item"}
    _SHELL_OPERATORS = re.compile(r"(?:\|\||&&|[|;&<>`]|\$\()")
    _CREDENTIAL_MARKERS = (
        ".env",
        ".git/",
        ".git\\",
        ".aegis",
        ".ssh",
        ".aws",
        ".azure",
        ".gcloud",
        ".kube",
        "id_rsa",
        "id_ed25519",
        "credentials",
    )

    def evaluate(self, command: str, workspace_root: Path) -> PolicyDecision:
        stripped = command.strip()
        if not stripped:
            return PolicyDecision(CommandTier.DENY, "Empty command.")
        lowered = stripped.casefold()
        if any(marker in lowered for marker in self._CREDENTIAL_MARKERS):
            return PolicyDecision(
                CommandTier.DENY, "Commands may not access credential or Aegis internal paths."
            )
        if self._SHELL_OPERATORS.search(stripped):
            return PolicyDecision(
                CommandTier.DENY,
                "Shell chaining, redirection, substitution, and pipelines are denied.",
            )
        try:
            argv = tuple(shlex.split(stripped, posix=os.name != "nt"))
        except ValueError as exc:
            return PolicyDecision(CommandTier.DENY, f"Command parsing failed: {exc}.")
        if not argv:
            return PolicyDecision(CommandTier.DENY, "Empty command.")

        executable = Path(argv[0].strip('"')).name.casefold()
        if executable.endswith(".exe"):
            executable = executable[:-4]
        if executable in self._DENIED_EXECUTABLES:
            return PolicyDecision(
                CommandTier.DENY, f"System or privilege command '{executable}' is denied.", argv
            )

        for token in argv[1:]:
            clean = token.strip("'\"")
            if clean in {"/", "\\", "/*"} or clean.startswith(("/", "\\")):
                return PolicyDecision(
                    CommandTier.DENY, "Command references root or system path.", argv
                )
            if ".." in clean.split("/") or ".." in clean.split("\\"):
                return PolicyDecision(CommandTier.DENY, "Command contains path traversal.", argv)
            candidate = Path(clean)
            if candidate.is_absolute():
                try:
                    validate_path(candidate, workspace_root)
                except (PathTraversalError, ValueError):
                    return PolicyDecision(
                        CommandTier.DENY, "Command references a path outside the workspace.", argv
                    )

        if executable in self._DELETE_EXECUTABLES:
            return PolicyDecision(
                CommandTier.REQUIRE_APPROVAL, "File deletion requires human approval.", argv
            )
        if executable in self._APPROVAL_EXECUTABLES:
            if (
                executable == "git"
                and len(argv) > 1
                and argv[1].casefold() in {"status", "diff", "log", "show", "branch"}
            ):
                return PolicyDecision(
                    CommandTier.AUTO_ALLOW, "Read-only git inspection is allowed.", argv
                )
            if (
                executable in {"pip", "pip3", "uv"}
                and len(argv) > 1
                and argv[1].casefold() in {"show", "list", "check"}
            ):
                return PolicyDecision(
                    CommandTier.AUTO_ALLOW, "Read-only package inspection is allowed.", argv
                )
            if executable == "npm" and len(argv) > 1 and argv[1].casefold() in {"test", "run"}:
                script = argv[2].casefold() if len(argv) > 2 else ""
                if argv[1].casefold() == "test" or script in {"test", "lint", "build", "typecheck"}:
                    return PolicyDecision(
                        CommandTier.AUTO_ALLOW, "Test, lint, build, or type-check command.", argv
                    )
            return PolicyDecision(
                CommandTier.REQUIRE_APPROVAL,
                f"Command '{executable}' may modify files or use the network.",
                argv,
            )

        if executable in {
            "python",
            "python3",
            "pytest",
            "ruff",
            "mypy",
            "eslint",
            "tsc",
            "go",
            "cargo",
        }:
            safe_test = executable == "pytest" or argv[1:3] == ("-m", "pytest")
            safe_test = safe_test or (
                executable in {"python", "python3"} and argv[1:3] == ("-m", "unittest")
            )
            if (
                executable in {"python", "python3"}
                and len(argv) > 1
                and argv[1].lower().endswith(".py")
            ):
                try:
                    validate_path(argv[1], workspace_root)
                    safe_test = True
                except (PathTraversalError, ValueError):
                    return PolicyDecision(
                        CommandTier.DENY, "Python script is outside the workspace.", argv
                    )
            safe_lint = executable in {"ruff", "mypy", "eslint", "tsc"}
            safe_language_test = (executable == "go" and argv[1:2] == ("test",)) or (
                executable == "cargo" and argv[1:2] == ("test",)
            )
            safe_version = any(arg in {"--version", "-V"} for arg in argv[1:])
            if safe_test or safe_lint or safe_language_test or safe_version:
                return PolicyDecision(
                    CommandTier.AUTO_ALLOW, "Test, lint, type-check, or version command.", argv
                )
            if executable.startswith("python") and "-c" in argv:
                return PolicyDecision(
                    CommandTier.REQUIRE_APPROVAL,
                    "Inline Python can access arbitrary data and requires approval.",
                    argv,
                )

        return PolicyDecision(
            CommandTier.REQUIRE_APPROVAL, "Command is not in the read-only/test allow-list.", argv
        )
