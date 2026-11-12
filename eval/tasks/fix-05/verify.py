import sys

try:
    from accumulator import add_item
    b1 = add_item("apple")
    b2 = add_item("banana")
    assert b1 == ["apple"], f"b1 corrupted: {b1}"
    assert b2 == ["banana"], f"b2 corrupted: {b2}"
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
