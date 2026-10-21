from auth.tokens import verify_token

def authenticate_request(t: str) -> bool:
    return verify_token(t)
