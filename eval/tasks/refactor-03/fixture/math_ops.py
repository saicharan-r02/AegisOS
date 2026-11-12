def factorial(n: int) -> int:
    # Needs iterative refactor for large n
    res = 1
    for i in range(2, n + 1):
        res *= i
    return res
