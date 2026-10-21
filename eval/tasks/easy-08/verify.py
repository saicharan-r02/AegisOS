import sys

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
