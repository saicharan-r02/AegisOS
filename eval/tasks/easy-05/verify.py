import sys

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
