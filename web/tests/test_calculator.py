import pytest
from calculator import add, subtract, multiply, divide
class TestAdd:
    def test_add_positive_integers(self) -> None:
        assert add(2, 3) == 5
    def test_add_negative_numbers(self) -> None:
        assert add(-1, -2) == -3
        assert add(-5, 3) == -2
    def test_add_zero(self) -> None:
        assert add(0, 0) == 0
        assert add(5, 0) == 5
        assert add(0, 7) == 7
    def test_add_floats(self) -> None:
        assert add(1.5, 2.5) == pytest.approx(4.0)
        assert add(0.1, 0.2) == pytest.approx(0.3)

class TestSubtract:
    def test_subtract_positive_integers(self) -> None:
        assert subtract(10, 4) == 6
    def test_subtract_negative_numbers(self) -> None:
        assert subtract(-3, -7) == 4
        assert subtract(5, -2) == 7
    def test_subtract_zero(self) -> None:
        assert subtract(0, 0) == 0
        assert subtract(5, 0) == 5
        assert subtract(0, 5) == -5
    def test_subtract_floats(self) -> None:
        assert subtract(5.5, 2.5) == pytest.approx(3.0)
        assert subtract(0.3, 0.1) == pytest.approx(0.2)

class TestMultiply:
    def test_multiply_positive_integers(self) -> None:
        assert multiply(3, 4) == 12
    def test_multiply_negative_numbers(self) -> None:
        assert multiply(-3, 4) == -12
        assert multiply(-3, -4) == 12
    def test_multiply_zero(self) -> None:
        assert multiply(0, 5) == 0
        assert multiply(5, 0) == 0
        assert multiply(0, 0) == 0
    def test_multiply_floats(self) -> None:
        assert multiply(2.5, 4.0) == pytest.approx(10.0)
        assert multiply(0.1, 0.2) == pytest.approx(0.02)

class TestDivide:
    def test_divide_positive_integers(self) -> None:
        assert divide(10, 2) == 5
    def test_divide_negative_numbers(self) -> None:
        assert divide(-10, 2) == -5
        assert divide(10, -2) == -5
        assert divide(-10, -2) == 5
    def test_divide_zero(self) -> None:
        assert divide(0, 5) == 0
    def test_divide_floats(self) -> None:
        assert divide(7.5, 2.5) == pytest.approx(3.0)
        assert divide(1.0, 3.0) == pytest.approx(0.3333333333333333)
    def test_divide_by_zero_raises(self) -> None:
        with pytest.raises(ZeroDivisionError):
            divide(10, 0)
