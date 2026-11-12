import sys

try:
    from pagination import paginate
    items = list(range(1, 21))  # 1 to 20
    assert paginate(items, 1, 5) == [1, 2, 3, 4, 5], f"Page 1 failed: {paginate(items, 1, 5)}"
    assert paginate(items, 2, 5) == [6, 7, 8, 9, 10], f"Page 2 failed: {paginate(items, 2, 5)}"
    assert paginate(items, 4, 5) == [16, 17, 18, 19, 20], f"Page 4 failed: {paginate(items, 4, 5)}"
    assert paginate(items, 5, 5) == [], f"Page 5 should be empty: {paginate(items, 5, 5)}"
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
