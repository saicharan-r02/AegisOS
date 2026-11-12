def safe_nested_get(d, keys, default=None):
    curr = d
    for k in keys:
        curr = curr[k]  # BUG: raises KeyError if missing
    return curr
