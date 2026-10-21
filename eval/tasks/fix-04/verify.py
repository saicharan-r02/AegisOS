import sys
try:
    from currency import format_cents
    assert format_cents(1050) == "$10.50"
    assert format_cents(5) == "$0.05"
    assert format_cents(0) == "$0.00"
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
