from typing import List
from aegis_os.judge.models import BenchmarkTask

def get_golden_dataset() -> List[BenchmarkTask]:
    return [
        BenchmarkTask(
            id="easy-01",
            goal="Write a Python function `add(a, b)` in `math_utils.py` that returns the sum of two numbers.",
            initial_files={},
            verification_script="""import sys
try:
    from math_utils import add
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
"""
        ),
        BenchmarkTask(
            id="easy-02",
            goal="Fix the bug in `calculator.py`. The `multiply` function currently adds instead of multiplying.",
            initial_files={
                "calculator.py": "def multiply(a, b):\n    return a + b\n"
            },
            verification_script="""import sys
try:
    from calculator import multiply
    assert multiply(3, 4) == 12
    assert multiply(0, 5) == 0
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
"""
        )
    ]
