import sys

try:
    from nested import safe_nested_get
    data = {"a": {"b": {"c": 42}}}
    assert safe_nested_get(data, ["a", "b", "c"]) == 42
    assert safe_nested_get(data, ["a", "x", "c"], default="missing") == "missing"
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
