import sys
try:
    from calculator import multiply
    assert multiply(3, 4) == 12, f"Expected 12, got {multiply(3, 4)}"
    assert multiply(0, 5) == 0, f"Expected 0, got {multiply(0, 5)}"
    assert multiply(-2, 6) == -12, f"Expected -12, got {multiply(-2, 6)}"
    assert multiply(2.5, 2) == 5.0, f"Expected 5.0, got {multiply(2.5, 2)}"
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
