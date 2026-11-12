from validators import Validator


def register_user(email: str) -> bool:
    return Validator.is_valid_email(email)
