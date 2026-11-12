"""Unit tests for Phase 11: AegisDoctor, CLI versioning, and environment pre-flights."""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis_os.cli.doctor import AegisDoctor
from aegis_os.cli.main import build_parser


class TestAegisDoctor:
    """Validate pre-flight diagnostics engine."""

    def test_doctor_runs_cleanly_on_current_workspace(self):
        doctor = AegisDoctor(workspace_root=".")
        # Diagnostics should execute without raising exceptions
        exit_code = doctor.run_diagnostics()
        assert exit_code in (0, 1)

    def test_doctor_catches_unwritable_directory(self, tmp_path: Path):
        # Point to a path that does not exist or has bad permissions
        bad_path = tmp_path / "nonexistent_subfolder" / "deep"
        doctor = AegisDoctor(workspace_root=bad_path)
        exit_code = doctor.run_diagnostics()
        assert exit_code == 1

    def test_cli_version_flag_configured(self):
        parser = build_parser()
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["--version"])
        assert exc.value.code == 0

    def test_cli_doctor_subcommand_configured(self):
        parser = build_parser()
        args = parser.parse_args(["doctor", "-w", "."])
        assert args.subcommand == "doctor"
        assert args.workspace == "."
