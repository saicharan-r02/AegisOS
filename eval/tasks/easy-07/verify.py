import sys

try:
    from dict_utils import merge_dicts
    base = {"a": 1, "b": {"x": 10, "y": 20}}
    override = {"b": {"y": 99, "z": 30}, "c": 3}
    merged = merge_dicts(base, override)
    assert merged["a"] == 1
    assert merged["c"] == 3
    assert merged["b"]["x"] == 10, f"Expected nested 'x'=10 preserved, got {merged['b']}"
    assert merged["b"]["y"] == 99, f"Expected nested 'y'=99 overwritten, got {merged['b']}"
    assert merged["b"]["z"] == 30, f"Expected nested 'z'=30 merged, got {merged['b']}"
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
