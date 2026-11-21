"""Run available local security scanners and normalize their JSON findings."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from aegis_os.kernel.context import redact_sensitive_text
from aegis_os.sandbox.path_guard import PathTraversalError, validate_path


class ScannerFinding(BaseModel):
    scanner: str
    rule_id: str
    severity: str
    file: str
    line: int | None = None
    description: str
    remediation: str = "Review and address this scanner finding."


class ScannerRun(BaseModel):
    scanner: str
    status: str
    findings_count: int = 0
    error: str | None = None


class ScannerReport(BaseModel):
    runs: list[ScannerRun] = Field(default_factory=list)
    findings: list[ScannerFinding] = Field(default_factory=list)

    @property
    def completed_scanners(self) -> int:
        return sum(run.status == "completed" for run in self.runs)


class SecurityScannerRunner:
    """Invoke installed scanners with fixed argv, timeout, and bounded output."""

    def __init__(
        self,
        workspace_root: Path,
        *,
        timeout_seconds: float = 120.0,
        allow_network_scanners: bool | None = None,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.timeout_seconds = timeout_seconds
        self.allow_network_scanners = (
            allow_network_scanners
            if allow_network_scanners is not None
            else self._read_network_setting()
        )

    def _read_network_setting(self) -> bool:
        config_path = self.workspace_root / "aegis.toml"
        if not config_path.is_file():
            return False
        try:
            with config_path.open("rb") as config_file:
                config = tomllib.load(config_file)
            return bool(config.get("security", {}).get("allow_network_scanners", False))
        except (OSError, tomllib.TOMLDecodeError, AttributeError):
            return False

    def run(self, target: str) -> ScannerReport:
        report = ScannerReport()
        try:
            target_path = validate_path(target, self.workspace_root)
        except (PathTraversalError, ValueError) as exc:
            return ScannerReport(
                runs=[ScannerRun(scanner="path_guard", status="error", error=str(exc))]
            )
        relative_target = target_path.relative_to(self.workspace_root).as_posix() or "."

        bandit = self._run_json("bandit", ["-r", relative_target, "-s", "B101", "-f", "json", "-q"])
        if bandit is None:
            report.runs.append(
                ScannerRun(scanner="bandit", status="missing", error="bandit is not installed.")
            )
        else:
            report.runs.append(bandit[0])
            report.findings.extend(self._parse_bandit(bandit[1]))

        secrets = self._run_json("detect-secrets", ["scan", "--all-files", relative_target])
        if secrets is None:
            report.runs.append(
                ScannerRun(
                    scanner="detect-secrets",
                    status="missing",
                    error="detect-secrets is not installed.",
                )
            )
        else:
            report.runs.append(secrets[0])
            report.findings.extend(self._parse_detect_secrets(secrets[1]))

        semgrep_config = Path(__file__).with_name("semgrep-rules.yml")
        semgrep = self._run_json(
            "semgrep",
            [
                "scan",
                "--config",
                str(semgrep_config),
                "--json",
                relative_target,
                "--disable-version-check",
            ],
        )
        if semgrep is None:
            report.runs.append(
                ScannerRun(scanner="semgrep", status="missing", error="semgrep is not installed.")
            )
        else:
            report.runs.append(semgrep[0])
            report.findings.extend(self._parse_semgrep(semgrep[1]))

        for scanner, args in self._network_scanner_commands(relative_target):
            if not self.allow_network_scanners:
                report.runs.append(
                    ScannerRun(
                        scanner=scanner,
                        status="skipped",
                        error="Network scanner is disabled by default.",
                    )
                )
                continue
            result = self._run_json(scanner, args)
            if result is None:
                report.runs.append(
                    ScannerRun(
                        scanner=scanner, status="missing", error=f"{scanner} is not installed."
                    )
                )
            else:
                report.runs.append(result[0])
                if scanner == "semgrep":
                    report.findings.extend(self._parse_semgrep(result[1]))
                elif scanner == "pip-audit":
                    report.findings.extend(self._parse_pip_audit(result[1]))
                else:
                    report.findings.extend(self._parse_npm_audit(result[1]))

        for run in report.runs:
            run.findings_count = sum(finding.scanner == run.scanner for finding in report.findings)
        return report

    @staticmethod
    def _network_scanner_commands(target: str) -> list[tuple[str, list[str]]]:
        commands = [
            ("pip-audit", ["--format", "json", "-r", "requirements.txt"]),
            ("npm-audit", ["audit", "--json"]),
        ]
        return commands

    PYTHON_MODULES: dict[str, str] = {
        "bandit": "bandit",
        "detect-secrets": "detect_secrets",
        "pip-audit": "pip_audit",
    }

    def _run_json(self, scanner: str, args: list[str]) -> tuple[ScannerRun, dict[str, Any]] | None:
        cmd: list[str] | None = None
        module_name = self.PYTHON_MODULES.get(scanner)
        if module_name and importlib.util.find_spec(module_name) is not None:
            cmd = [sys.executable, "-m", module_name, *args]
        else:
            executable = shutil.which(scanner)
            if executable is None and os.name == "nt":
                candidate = Path(sys.executable).parent / f"{scanner}.exe"
                if candidate.is_file():
                    executable = str(candidate)
            if executable is not None:
                cmd = [executable, *args]

        if cmd is None:
            return None

        try:
            result = subprocess.run(
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except OSError as exc:
            if module_name and cmd[0] != sys.executable:
                try:
                    result = subprocess.run(
                        [sys.executable, "-m", module_name, *args],
                        cwd=self.workspace_root,
                        capture_output=True,
                        text=True,
                        timeout=self.timeout_seconds,
                        check=False,
                    )
                except (OSError, subprocess.TimeoutExpired) as inner_exc:
                    return ScannerRun(
                        scanner=scanner, status="error", error=redact_sensitive_text(str(inner_exc))
                    ), {}
            else:
                return ScannerRun(
                    scanner=scanner, status="error", error=redact_sensitive_text(str(exc))
                ), {}
        except subprocess.TimeoutExpired as exc:
            return ScannerRun(
                scanner=scanner, status="error", error=redact_sensitive_text(str(exc))
            ), {}
        output = result.stdout[:2_000_000]
        try:
            parsed = json.loads(output) if output.strip() else {}
        except json.JSONDecodeError:
            run = ScannerRun(
                scanner=scanner,
                status="error",
                error=redact_sensitive_text(result.stderr or "Scanner returned invalid JSON.")[
                    :500
                ],
            )
            return run, {}
        run = ScannerRun(
            scanner=scanner,
            status="completed" if result.returncode in (0, 1) else "error",
            error=redact_sensitive_text(result.stderr)[:500]
            if result.returncode not in (0, 1)
            else None,
        )
        return run, parsed

    def _parse_bandit(self, data: dict[str, Any]) -> list[ScannerFinding]:
        findings = []
        for item in data.get("results", []):
            findings.append(
                ScannerFinding(
                    scanner="bandit",
                    rule_id=str(item.get("test_id", "BANDIT")),
                    severity=str(item.get("issue_severity", "MEDIUM")).upper(),
                    file=self._relative_file(str(item.get("filename", ""))),
                    line=item.get("line_number"),
                    description=redact_sensitive_text(
                        str(item.get("issue_text", "Security issue"))
                    ),
                    remediation=redact_sensitive_text(
                        str(item.get("more_info", "Review the Bandit finding."))
                    ),
                )
            )
        return findings

    def _parse_detect_secrets(self, data: dict[str, Any]) -> list[ScannerFinding]:
        findings: list[ScannerFinding] = []
        results = data.get("results", {})
        if not isinstance(results, dict):
            return findings
        for file_name, secrets in results.items():
            for item in secrets if isinstance(secrets, list) else []:
                findings.append(
                    ScannerFinding(
                        scanner="detect-secrets",
                        rule_id=str(item.get("type", "SECRET")),
                        severity="HIGH",
                        file=self._relative_file(str(file_name)),
                        line=item.get("line_number"),
                        description="Potential secret detected; the secret value is withheld.",
                        remediation="Rotate the credential and remove it from source control.",
                    )
                )
        return findings

    def _parse_semgrep(self, data: dict[str, Any]) -> list[ScannerFinding]:
        findings = []
        for item in data.get("results", []):
            extra = item.get("extra", {})
            findings.append(
                ScannerFinding(
                    scanner="semgrep",
                    rule_id=str(item.get("check_id", "SEMGREP")),
                    severity=str(extra.get("severity", "MEDIUM")).upper(),
                    file=self._relative_file(str(item.get("path", ""))),
                    line=item.get("start", {}).get("line"),
                    description=redact_sensitive_text(
                        str(extra.get("message", "Security finding"))
                    ),
                )
            )
        return findings

    def _parse_pip_audit(self, data: dict[str, Any]) -> list[ScannerFinding]:
        findings = []
        for dependency in data.get("dependencies", []):
            for vulnerability in dependency.get("vulns", []):
                findings.append(
                    ScannerFinding(
                        scanner="pip-audit",
                        rule_id=str(vulnerability.get("id", "UNKNOWN")),
                        severity="HIGH",
                        file="requirements.txt",
                        description=redact_sensitive_text(
                            f"{dependency.get('name')} {dependency.get('version')}: {vulnerability.get('description', 'Vulnerable dependency')}"
                        ),
                        remediation="Upgrade to a fixed version: "
                        + ", ".join(vulnerability.get("fix_versions", [])),
                    )
                )
        return findings

    def _parse_npm_audit(self, data: dict[str, Any]) -> list[ScannerFinding]:
        findings = []
        for name, item in data.get("vulnerabilities", {}).items():
            findings.append(
                ScannerFinding(
                    scanner="npm-audit",
                    rule_id=name,
                    severity=str(item.get("severity", "high")).upper(),
                    file="package-lock.json",
                    description=redact_sensitive_text(str(item.get("via", []))),
                    remediation=redact_sensitive_text(
                        str(item.get("fixAvailable", "Run npm audit fix after review."))
                    ),
                )
            )
        return findings

    def _relative_file(self, path: str) -> str:
        try:
            candidate = Path(path)
            resolved = (
                candidate.resolve()
                if candidate.is_absolute()
                else (self.workspace_root / candidate).resolve()
            )
            return resolved.relative_to(self.workspace_root).as_posix()
        except (OSError, ValueError):
            return "[outside workspace]"
