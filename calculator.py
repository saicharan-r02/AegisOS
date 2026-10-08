"""AegisOS Calculator Module.

Provides basic arithmetic operations: add, subtract, multiply, and divide.
"""


def add(a: float, b: float) -> float:
    """Return the sum of two numbers.

    Args:
        a: First operand.
        b: Second operand.

    Returns:
        The sum of a and b.
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
        The product of a and b.
    """
    return a * b


def divide(a: float, b: float) -> float:
    """Return the quotient of two numbers.

    Args:
        a: Dividend.
        b: Divisor.

    Returns:
        The result of a / b.

    Raises:
        ZeroDivisionError: If b is zero.
    """
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero.")
    return a / b
