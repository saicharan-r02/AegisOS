import json
import shutil
from pathlib import Path

TASKS = [
    {
        "id": "easy-01",
        "category": "feature",
        "goal": "Write a Python function `add(a, b)` in `math_utils.py` that returns the sum of two numbers.",
        "initial_files": {
            "math_utils.py": '\"\"\"Math utilities module.\"\"\"\n'
        },
        "verification_script": """import sys
try:
    from math_utils import add
    assert add(2, 3) == 5, f"Expected 5, got {add(2, 3)}"
    assert add(-1, 1) == 0, f"Expected 0, got {add(-1, 1)}"
    assert add(0, 0) == 0, f"Expected 0, got {add(0, 0)}"
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
"""
    },
    {
        "id": "easy-02",
        "category": "bugfix",
        "goal": "Fix the bug in `calculator.py`. The `multiply` function currently adds instead of multiplying.",
        "initial_files": {
            "calculator.py": "def multiply(a: float, b: float) -> float:\n    # BUG: mistakenly uses addition\n    return a + b\n"
        },
        "verification_script": """import sys
try:
    from calculator import multiply
    assert multiply(3, 4) == 12, f"Expected 12, got {multiply(3, 4)}"
    assert multiply(0, 5) == 0, f"Expected 0, got {multiply(0, 5)}"
    assert multiply(-2, 6) == -12, f"Expected -12, got {multiply(-2, 6)}"
    assert multiply(2.5, 2) == 5.0, f"Expected 5.0, got {multiply(2.5, 2)}"
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
"""
    },
    {
        "id": "easy-03",
        "category": "bugfix",
        "goal": "Fix the 1-indexed pagination calculation in `pagination.py`. Currently it miscalculates page boundaries.",
        "initial_files": {
            "pagination.py": """from typing import Any, List

def paginate(items: List[Any], page: int, page_size: int) -> List[Any]:
    \"\"\"Return items for a 1-indexed page number.\"\"\"
    # BUG: Using 0-indexed formula for 1-indexed page
    start = page * page_size
    end = start + page_size
    return items[start:end]
"""
        },
        "verification_script": """import sys
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
"""
    },
    {
        "id": "easy-04",
        "category": "feature",
        "goal": "In `string_utils.py`, implement `reverse_string(s: str) -> str` that returns the reversed string.",
        "initial_files": {
            "string_utils.py": '\"\"\"String utilities module.\"\"\"\n'
        },
        "verification_script": """import sys
try:
    from string_utils import reverse_string
    assert reverse_string("hello") == "olleh"
    assert reverse_string("") == ""
    assert reverse_string("a") == "a"
    assert reverse_string("racecar") == "racecar"
    assert reverse_string("123 456") == "654 321"
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
"""
    },
    {
        "id": "easy-05",
        "category": "feature",
        "goal": "In `palindrome.py`, implement `is_palindrome(s: str) -> bool` that checks if a string is a palindrome, ignoring non-alphanumeric characters and case.",
        "initial_files": {
            "palindrome.py": '\"\"\"Palindrome verification utility.\"\"\"\n'
        },
        "verification_script": """import sys
try:
    from palindrome import is_palindrome
    assert is_palindrome("A man, a plan, a canal: Panama") is True
    assert is_palindrome("race a car") is False
    assert is_palindrome("") is True
    assert is_palindrome("No 'x' in Nixon") is True
    assert is_palindrome("Was it a car or a cat I saw?") is True
    assert is_palindrome("12321") is True
    assert is_palindrome("12345") is False
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
"""
    },
    {
        "id": "easy-06",
        "category": "refactor",
        "goal": "Refactor `pricing.py` to extract magic numbers 0.08 and 0.15 into module constants `DEFAULT_TAX_RATE = 0.08` and `DEFAULT_DISCOUNT_RATE = 0.15`. `calculate_total` should use these constants.",
        "initial_files": {
            "pricing.py": """def calculate_total(subtotal: float, apply_discount: bool = False) -> float:
    discount = subtotal * 0.15 if apply_discount else 0.0
    discounted = subtotal - discount
    tax = discounted * 0.08
    return round(discounted + tax, 2)
"""
        },
        "verification_script": """import sys
try:
    import pricing
    assert hasattr(pricing, "DEFAULT_TAX_RATE"), "DEFAULT_TAX_RATE constant missing"
    assert hasattr(pricing, "DEFAULT_DISCOUNT_RATE"), "DEFAULT_DISCOUNT_RATE constant missing"
    assert pricing.DEFAULT_TAX_RATE == 0.08, f"Wrong DEFAULT_TAX_RATE: {pricing.DEFAULT_TAX_RATE}"
    assert pricing.DEFAULT_DISCOUNT_RATE == 0.15, f"Wrong DEFAULT_DISCOUNT_RATE: {pricing.DEFAULT_DISCOUNT_RATE}"
    assert pricing.calculate_total(100.0, False) == 108.0
    assert pricing.calculate_total(100.0, True) == 91.80
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
"""
    },
    {
        "id": "easy-07",
        "category": "bugfix",
        "goal": "Fix `merge_dicts` in `dict_utils.py`. It currently performs a shallow update that overwrites nested dictionaries instead of deeply and recursively merging them.",
        "initial_files": {
            "dict_utils.py": """from typing import Any, Dict

def merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    # BUG: Shallow merge destroys nested keys
    result = base.copy()
    result.update(override)
    return result
"""
        },
        "verification_script": """import sys
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
"""
    },
    {
        "id": "easy-08",
        "category": "feature",
        "goal": "In `slugify.py`, implement `slugify(text: str) -> str` that converts a string to a URL-friendly slug: lowercase, removes punctuation/special characters, replaces spaces and underscores with hyphens, and strips leading/trailing hyphens.",
        "initial_files": {
            "slugify.py": '\"\"\"URL slug utility.\"\"\"\n'
        },
        "verification_script": """import sys
try:
    from slugify import slugify
    assert slugify("Hello World!") == "hello-world", f"Got: {slugify('Hello World!')}"
    assert slugify("---Leading & Trailing---") == "leading-trailing", f"Got: {slugify('---Leading & Trailing---')}"
    assert slugify("Python_3.11 is GREAT") == "python-311-is-great", f"Got: {slugify('Python_3.11 is GREAT')}"
    assert slugify("multiple    spaces   here") == "multiple-spaces-here", f"Got: {slugify('multiple    spaces   here')}"
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
"""
    },
    {
        "id": "easy-09",
        "category": "bugfix",
        "goal": "Fix `split_csv_line` in `csv_utils.py`. It naively splits by comma, which breaks when commas appear inside quotes. Return a list of parsed string fields.",
        "initial_files": {
            "csv_utils.py": """from typing import List

def split_csv_line(line: str) -> List[str]:
    # BUG: Naive split breaks on quoted commas
    return [col.strip() for col in line.split(",")]
"""
        },
        "verification_script": """import sys
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
"""
    },
    {
        "id": "easy-10",
        "category": "bugfix",
        "goal": "Fix `is_leap_year` in `calendar_utils.py`. It currently checks `year % 4 == 0`, failing on century years (e.g. 1900 is not a leap year, 2000 is a leap year).",
        "initial_files": {
            "calendar_utils.py": """def is_leap_year(year: int) -> bool:
    # BUG: Missing century rules
    return year % 4 == 0
"""
        },
        "verification_script": """import sys
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
"""
    }
]

def main():
    tasks_dir = Path("eval/tasks").resolve()
    # Clean previous task directories if any
    if tasks_dir.exists():
        shutil.rmtree(tasks_dir)
    tasks_dir.mkdir(parents=True, exist_ok=True)

    for t in TASKS:
        tdir = tasks_dir / t["id"]
        tdir.mkdir(parents=True, exist_ok=True)

        meta = {
            "id": t["id"],
            "category": t["category"],
            "goal": t["goal"]
        }
        (tdir / "task.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        fixture_dir = tdir / "fixture"
        fixture_dir.mkdir(parents=True, exist_ok=True)
        for rel_path, content in t["initial_files"].items():
            fpath = fixture_dir / rel_path
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")

        (tdir / "verify.py").write_text(t["verification_script"], encoding="utf-8")
        print(f"Created eval task: {t['id']} [{t['category']}] - {t['goal'][:60]}...")

if __name__ == "__main__":
    main()
