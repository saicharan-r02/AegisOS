import sys
try:
    code = open("types.ts").read()
    assert "interface UserProfile" in code
    assert "email: string" in code
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
