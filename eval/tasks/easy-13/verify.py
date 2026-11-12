import sys

try:
    from lists import flatten
    assert flatten([1, [2, [3, 4], 5], 6]) == [1, 2, 3, 4, 5, 6]
    assert flatten([]) == []
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
