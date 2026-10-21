import sys
try:
    from date_utils import parse_iso_date
    res = parse_iso_date("2026-10-21")
    assert res == {"year": 2026, "month": 10, "day": 21}
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
