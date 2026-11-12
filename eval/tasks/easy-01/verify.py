import sys

try:
    from math_utils import add
    assert add(2, 3) == 5, f"Expected 5, got {add(2, 3)}"
    assert add(-1, 1) == 0, f"Expected 0, got {add(-1, 1)}"
    assert add(0, 0) == 0, f"Expected 0, got {add(0, 0)}"
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
