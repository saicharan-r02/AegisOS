import pytest
from Aegis_OS.kernel.sandbox import SandboxExecutor

def test_sandbox_successful_command():
    executor=SandboxExecutor()
    res=executor.run_command('python -c "print(10 + 20)"')
    assert res.is_success is True
    assert res.exit_code==0
    assert res.stdout=="30"
    assert res.timed_out is False

def test_sandbox_timeout():
    executor=SandboxExecutor(default_timeout=1)
    # Command that sleeps for 3 seconds should timeout
    res=executor.run_command('python -c "import time; time.sleep(3)"',timeout=1)
    assert res.timed_out is True
    assert res.is_success is False
    assert "timed out" in res.stderr.lower()