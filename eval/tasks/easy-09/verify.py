import sys

try:
    from csv_utils import split_csv_line
    res1 = split_csv_line("apple,banana,cherry")
    assert res1 == ["apple", "banana", "cherry"], f"Failed simple: {res1}"
    res2 = split_csv_line('1,"Doe, John",Engineer')
    assert res2 == ["1", "Doe, John", "Engineer"], f"Failed quoted: {res2}"
    res3 = split_csv_line('"Smith, Jane, Jr.",42,"Boston, MA"')
    assert res3 == ["Smith, Jane, Jr.", "42", "Boston, MA"], f"Failed multi-quoted: {res3}"
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
