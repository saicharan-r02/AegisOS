def verify_token(t: str) -> bool:
    return t.startswith('bearer-valid-')
