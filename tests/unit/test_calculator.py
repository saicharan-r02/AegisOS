import pytest
from calculator import add, subtract, multiply, divide


class TestAdd:
    def test_add_positive(self):
        assert add(2, 3) == 5

    def test_add_negative(self):
        assert add(-1, -1) == -2

    def test_add_zero(self):
        assert add(0, 0) == 0

    def test_add_floats(self):
        assert add(0.1, 0.2) == pytest.approx(0.3)


class TestSubtract:
    def test_subtract_positive(self):
        assert subtract(5, 3) == 2

    def test_subtract_negative(self):
        assert subtract(-5, -3) == -2

    def test_subtract_zero(self):
        assert subtract(0, 0) == 0

    def test_subtract_floats(self):
        assert subtract(1.0, 0.5) == pytest.approx(0.5)


class TestMultiply:
    def test_multiply_positive(self):
        assert multiply(3, 4) == 12

    def test_multiply_negative(self):
        assert multiply(-3, 4) == -12

    def test_multiply_zero(self):
        assert multiply(5, 0) == 0

    def test_multiply_floats(self):
        assert multiply(0.5, 0.5) == pytest.approx(0.25)


class TestDivide:
    def test_divide_positive(self):
        assert divide(10, 2) == 5

    def test_divide_negative(self):
        assert divide(-10, 2) == -5

    def test_divide_floats(self):
        assert divide(1.0, 3.0) == pytest.approx(0.3333333, rel=1e-6)

    def test_divide_by_zero(self):
        with pytest.raises(ValueError, match="Cannot divide by zero"):
            divide(10, 0)
