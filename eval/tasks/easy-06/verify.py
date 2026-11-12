import sys

try:
    import pricing
    assert hasattr(pricing, "DEFAULT_TAX_RATE"), "DEFAULT_TAX_RATE constant missing"
    assert hasattr(pricing, "DEFAULT_DISCOUNT_RATE"), "DEFAULT_DISCOUNT_RATE constant missing"
    assert pricing.DEFAULT_TAX_RATE == 0.08, f"Wrong DEFAULT_TAX_RATE: {pricing.DEFAULT_TAX_RATE}"
    assert pricing.DEFAULT_DISCOUNT_RATE == 0.15, f"Wrong DEFAULT_DISCOUNT_RATE: {pricing.DEFAULT_DISCOUNT_RATE}"
    assert pricing.calculate_total(100.0, False) == 108.0
    assert pricing.calculate_total(100.0, True) == 91.80
    print("PASS")
    sys.exit(0)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
