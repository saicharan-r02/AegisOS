import sys
try:
    from stats import calculate_mean
    assert calculate_mean([2.0, 4.0]) == 3.0
    assert calculate_mean([]) == 0.0
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
