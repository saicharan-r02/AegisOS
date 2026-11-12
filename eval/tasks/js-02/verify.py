import sys

try:
    code = open("slug.js").read()
    assert "slugify" in code
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
