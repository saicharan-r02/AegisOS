"""Basic arithmetic helpers.

This module exposes four small, dependency-free functions that implement the
most common arithmetic operations.  They are intentionally thin wrappers
around the corresponding Python operators so that they are trivial to read,
reuse and unit test.

Example:
    >>> from calculator import add, divide
    >>> add(2, 3)
    5
    >>> divide(10, 4)
    2.5
"""

from __future__ import annotations

__all__ = ["add", "subtract", "multiply", "divide"]

#: Any numeric type accepted by the calculator functions.
Number = int | float


def add(a: Number, b: Number) -> Number:
    """Return the sum of *a* and *b*.

    Args:
        a: First operand.
        b: Second operand.

    Returns:
        The result of ``a + b``.

    Raises:
        TypeError: If either operand is not a number.
    """
    return a + b


def subtract(a: Number, b: Number) -> Number:
    """Return the difference of *a* and *b*.

    Args:
        a: Minuend.
        b: Subtrahend.

    Returns:
        The result of ``a - b``.

    Raises:
        TypeError: If either operand is not a number.
    """
    return a - b


def multiply(a: Number, b: Number) -> Number:
    """Return the product of *a* and *b*.

    Args:
        a: First factor.
        b: Second factor.

    Returns:
        The result of ``a * b``.

    Raises:
        TypeError: If either operand is not a number.
    """
    return a * b


def divide(a: Number, b: Number) -> float:
    """Return the quotient of *a* divided by *b*.

    Args:
        a: Dividend.
        b: Divisor. Must not be zero.

    Returns:
        The result of ``a / b`` as a floating point number.

    Raises:
        ValueError: If *b* is zero (including ``0.0`` and ``-0.0``).
        TypeError: If either operand is not a number.
    """
    if b == 0:
        raise ValueError("Cannot divide by zero.")
    return a / b
