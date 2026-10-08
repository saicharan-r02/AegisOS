"""AegisOS Calculator Module.

Provides basic arithmetic operations: addition, subtraction, multiplication,
and division. All functions accept numeric arguments (int or float) and
return the corresponding result.
"""


def add(a: float, b: float) -> float:
    """Return the sum of two numbers.

    Args:
        a: First operand.
        b: Second operand.

    Returns:
        The result of a + b.
    """
    return a + b


def subtract(a: float, b: float) -> float:
    """Return the difference of two numbers.

    Args:
        a: First operand (minuend).
        b: Second operand (subtrahend).

    Returns:
        The result of a - b.
    """
    return a - b


def multiply(a: float, b: float) -> float:
    """Return the product of two numbers.

    Args:
        a: First operand.
        b: Second operand.

    Returns:
        The result of a * b.
    """
    return a * b


def divide(a: float, b: float) -> float:
    """Return the quotient of two numbers.

    Args:
        a: Dividend.
        b: Divisor. Must not be zero.

    Returns:
        The result of a / b.

    Raises:
        ValueError: If b is zero.
    """
    if b == 0:
        raise ValueError("Cannot divide by zero.")
    return a / b
