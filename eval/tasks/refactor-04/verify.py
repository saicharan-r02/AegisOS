import sys
import types
try:
    from pipeline import process_numbers
    res = process_numbers([1, 2, 3, 4, 5])
    assert isinstance(res, types.GeneratorType)
    assert list(res) == [4, 8]
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
