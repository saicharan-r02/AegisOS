import sys
try:
    from math_ops import factorial
    assert factorial(5) == 120
    assert factorial(0) == 1
    assert factorial(20) == 2432902008176640000
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
