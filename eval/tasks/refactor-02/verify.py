import sys
try:
    from validators import Validator
    from user_service import register_user
    assert Validator.is_valid_email("admin@aegis.os") is True
    assert register_user("bademail") is False
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
