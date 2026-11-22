"""workspace_audit compares test files against the commit a mission started from."""
import subprocess
from pathlib import Path

import pytest

from aegis_os.orchestration.invariants import HardInvariantEngine
from aegis_os.verification.workspace_audit import audit_test_changes, current_commit, is_test_file

ORIGINAL = (
    "def test_add():\n    assert 1 + 1 == 2\n    assert 2 + 2 == 4\n\n"
    "def test_sub():\n    assert 3 - 1 == 2\n"
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_math.py").write_text(ORIGINAL)
    (tmp_path / "app.py").write_text("x = 1\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def test_is_test_file():
    assert is_test_file("tests/test_math.py")
    assert is_test_file("pkg/math_test.py")
    assert not is_test_file("app.py")
    assert not is_test_file("tests/data.json")


def test_no_git_commit_skips_without_blocking(tmp_path: Path):
    assert current_commit(tmp_path) is None
    ok, notes = audit_test_changes(tmp_path, None, "x")
    assert ok and "skipped" in notes[0]


def test_untouched_tests_pass(repo: Path):
    base = current_commit(repo)
    (repo / "app.py").write_text("x = 2\n")
    assert audit_test_changes(repo, base, "change app") == (True, [])


def test_deleted_test_function_is_caught(repo: Path):
    base = current_commit(repo)
    (repo / "tests" / "test_math.py").write_text("def test_add():\n    assert 1 + 1 == 2\n    assert 2 + 2 == 4\n")
    ok, violations = audit_test_changes(repo, base, "make it faster")
    assert not ok
    assert any("TEST DELETION" in v and "test_sub" in v for v in violations)


def test_deleted_test_file_is_caught(repo: Path):
    base = current_commit(repo)
    (repo / "tests" / "test_math.py").unlink()
    ok, violations = audit_test_changes(repo, base, "tidy up")
    assert not ok and violations


def test_weakened_assertion_is_caught(repo: Path):
    base = current_commit(repo)
    (repo / "tests" / "test_math.py").write_text(
        "def test_add():\n    assert True\n\ndef test_sub():\n    assert 3 - 1 == 2\n"
    )
    ok, violations = audit_test_changes(repo, base, "fix the bug")
    assert not ok
    assert any("ASSERTION WEAKENING" in v or "TRIVIAL" in v for v in violations)


def test_new_test_file_is_allowed(repo: Path):
    base = current_commit(repo)
    (repo / "tests" / "test_new.py").write_text("def test_new():\n    assert 1\n")
    _git(repo, "add", "-A")
    assert audit_test_changes(repo, base, "add tests")[0] is True


def test_objective_can_explicitly_allow_test_edits(repo: Path):
    base = current_commit(repo)
    (repo / "tests" / "test_math.py").write_text("def test_add():\n    assert 1 + 1 == 2\n    assert 2 + 2 == 4\n")
    ok, _ = audit_test_changes(repo, base, "fix test for sub")
    assert ok


def test_committed_changes_during_mission_are_still_detected(repo: Path):
    """Dev commits as it goes, so comparison must be against the START commit, not HEAD."""
    base = current_commit(repo)
    (repo / "tests" / "test_math.py").write_text("def test_add():\n    assert 1 + 1 == 2\n    assert 2 + 2 == 4\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "dev commit")
    ok, violations = audit_test_changes(repo, base, "speed up")
    assert not ok and violations


def test_invariant_gate_reports_the_real_violation_text():
    passed, results = HardInvariantEngine.evaluate(
        qa_report=None, sec_report=None, test_integrity_passed=False,
        test_integrity_details="tests/test_math.py: TEST DELETION DETECTED",
    )
    failing = [r for r in results if r.name == "INVARIANT_4_TEST_INTEGRITY"][0]
    assert not failing.passed and "TEST DELETION" in failing.details
