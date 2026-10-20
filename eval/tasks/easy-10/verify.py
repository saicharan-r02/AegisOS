import sys
try:
    from calendar_utils import is_leap_year
    assert is_leap_year(2024) is True, "2024 should be leap"
    assert is_leap_year(2023) is False, "2023 should not be leap"
    assert is_leap_year(2000) is True, "2000 should be leap (divisible by 400)"
    assert is_leap_year(1900) is False, "1900 should not be leap (divisible by 100 but not 400)"
    assert is_leap_year(2100) is False, "2100 should not be leap"
    assert is_leap_year(2400) is True, "2400 should be leap"
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
