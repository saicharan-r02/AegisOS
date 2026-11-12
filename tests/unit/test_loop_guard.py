from aegis_os.kernel.loop_guard import LoopGuard


def test_loop_guard_detects_identical_calls_and_escalates() -> None:
    guard = LoopGuard(repeat_limit=2, escalation_after=2)
    assert guard.observe("write_file", {"path": "a.py"}, made_progress=True) is None

    first = guard.observe("write_file", {"path": "a.py"}, made_progress=True)
    second = guard.observe("write_file", {"path": "a.py"}, made_progress=True)

    assert first is not None and first.should_reflect and not first.should_escalate
    assert second is not None and second.should_escalate


def test_loop_guard_detects_two_call_oscillation() -> None:
    guard = LoopGuard()
    assert guard.observe("read_file", {"path": "a.py"}, made_progress=True) is None
    assert guard.observe("write_file", {"path": "a.py"}, made_progress=True) is None
    assert guard.observe("read_file", {"path": "a.py"}, made_progress=True) is None

    signal = guard.observe("write_file", {"path": "a.py"}, made_progress=True)

    assert signal is not None
    assert "Alternated" in signal.reason


def test_loop_guard_detects_no_progress_window() -> None:
    guard = LoopGuard(repeat_limit=4, oscillation_window=4)
    for index in range(3):
        assert guard.observe(f"run_tests_{index}", {}, made_progress=False) is None

    signal = guard.observe("read_file", {"path": "a.py"}, made_progress=False)

    assert signal is not None
    assert "no progress" in signal.reason
