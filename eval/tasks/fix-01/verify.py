import sys
try:
    from search import binary_search
    arr = [2, 5, 8, 12, 16, 23, 38, 56, 72, 91]
    assert binary_search(arr, 23) == 5
    assert binary_search(arr, 2) == 0
    assert binary_search(arr, 91) == 9
    assert binary_search(arr, 100) == -1
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
