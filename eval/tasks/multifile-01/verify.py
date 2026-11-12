import sys

try:
    from auth.middleware import authenticate_request
    assert authenticate_request("bearer-valid-12345") is True
    assert authenticate_request("invalid-token") is False
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
