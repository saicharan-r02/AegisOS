"""Calculator module providing basic arithmetic operations.

This module exposes four functions — :func:`add`, :func:`subtract`,
:func:`multiply`, and :func:`divide` — that perform the corresponding
arithmetic operation on two numeric operands.
"""


def add(a: float, b: float) -> float:
    """Return the sum of *a* and *b*.

    Args:
        a: First operand.
        b: Second operand.

    Returns:
        The result of ``a + b``.
    """
    return a + b


def subtract(a: float, b: float) -> float:
    """Return the difference of *a* and *b*.

    Args:
        a: Minuend.
        b: Subtrahend.

    Returns:
        The result of ``a - b``.
    """
    return a - b


def multiply(a: float, b: float) -> float:
    """Return the product of *a* and *b*.

    Args:
        a: First factor.
        b: Second factor.

    Returns:
        The result of ``a * b``.
    """
    return a * b


def divide(a: float, b: float) -> float:
    """Return the quotient of *a* divided by *b*.

    Args:
        a: Dividend.
        b: Divisor. Must not be zero.

    Returns:
        The result of ``a / b``.

    Raises:
        ValueError: If *b* is zero.
    """
    if b == 0:
        raise ValueError("Cannot divide by zero.")
    return a / b
