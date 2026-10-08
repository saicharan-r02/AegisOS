"""Pytest tests for the calculator module.

Covers add, subtract, multiply, and divide functions with:
- Basic arithmetic (positive integers)
- Negative numbers
- Zero operands
- Float operands
- Division by zero exception
"""

import pytest

from calculator import add, subtract, multiply, divide


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------

class TestAdd:
    """Tests for the add function."""

    def test_add_positive_integers(self) -> None:
        """Basic addition of two positive integers."""
        assert add(2, 3) == 5

    def test_add_negative_numbers(self) -> None:
        """Addition involving negative numbers."""
        assert add(-1, -2) == -3
        assert add(-5, 3) == -2

    def test_add_zero(self) -> None:
        """Addition with zero operands."""
        assert add(0, 0) == 0
        assert add(5, 0) == 5
        assert add(0, 7) == 7

    def test_add_floats(self) -> None:
        """Addition with float operands."""
        assert add(1.5, 2.5) == pytest.approx(4.0)
        assert add(0.1, 0.2) == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# subtract
# ---------------------------------------------------------------------------

class TestSubtract:
    """Tests for the subtract function."""

    def test_subtract_positive_integers(self) -> None:
        """Basic subtraction of two positive integers."""
        assert subtract(10, 4) == 6

    def test_subtract_negative_numbers(self) -> None:
        """Subtraction involving negative numbers."""
        assert subtract(-3, -7) == 4
        assert subtract(5, -2) == 7

    def test_subtract_zero(self) -> None:
        """Subtraction with zero operands."""
        assert subtract(0, 0) == 0
        assert subtract(5, 0) == 5
        assert subtract(0, 5) == -5

    def test_subtract_floats(self) -> None:
        """Subtraction with float operands."""
        assert subtract(5.5, 2.5) == pytest.approx(3.0)
        assert subtract(0.3, 0.1) == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# multiply
# ---------------------------------------------------------------------------

class TestMultiply:
    """Tests for the multiply function."""

    def test_multiply_positive_integers(self) -> None:
        """Basic multiplication of two positive integers."""
        assert multiply(3, 4) == 12

    def test_multiply_negative_numbers(self) -> None:
        """Multiplication involving negative numbers."""
        assert multiply(-3, 4) == -12
        assert multiply(-3, -4) == 12

    def test_multiply_zero(self) -> None:
        """Multiplication with zero operands."""
        assert multiply(0, 5) == 0
        assert multiply(5, 0) == 0
        assert multiply(0, 0) == 0

    def test_multiply_floats(self) -> None:
        """Multiplication with float operands."""
        assert multiply(2.5, 4.0) == pytest.approx(10.0)
        assert multiply(0.1, 0.2) == pytest.approx(0.02)


# ---------------------------------------------------------------------------
# divide
# ---------------------------------------------------------------------------

class TestDivide:
    """Tests for the divide function."""

    def test_divide_positive_integers(self) -> None:
        """Basic division of two positive integers."""
        assert divide(10, 2) == 5

    def test_divide_negative_numbers(self) -> None:
        """Division involving negative numbers."""
        assert divide(-10, 2) == -5
        assert divide(10, -2) == -5
        assert divide(-10, -2) == 5

    def test_divide_zero(self) -> None:
        """Division with zero as the dividend."""
        assert divide(0, 5) == 0

    def test_divide_floats(self) -> None:
        """Division with float operands."""
        assert divide(7.5, 2.5) == pytest.approx(3.0)
        assert divide(1.0, 3.0) == pytest.approx(0.3333333333333333)

    def test_divide_by_zero_raises(self) -> None:
        """Division by zero must raise a ZeroDivisionError."""
        with pytest.raises(ZeroDivisionError):
            divide(10, 0)
