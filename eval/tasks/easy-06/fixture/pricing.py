def calculate_total(subtotal: float, apply_discount: bool = False) -> float:
    discount = subtotal * 0.15 if apply_discount else 0.0
    discounted = subtotal - discount
    tax = discounted * 0.08
    return round(discounted + tax, 2)
