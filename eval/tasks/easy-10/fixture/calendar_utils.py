def is_leap_year(year: int) -> bool:
    # BUG: Missing century rules
    return year % 4 == 0
