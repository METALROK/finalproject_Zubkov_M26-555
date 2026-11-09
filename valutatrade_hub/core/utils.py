import hashlib
import secrets

SALT_LENGTH_BYTES = 8


def generate_salt() -> str:
    """
    Сгенерировать случайную соль для хеширования пароля.
    """
    return secrets.token_hex(SALT_LENGTH_BYTES)

def hash_password(password: str, salt: str) -> str:
    """
    Вернуть односторонний хеш SHA-256 от пароля с солью.
    """
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()

def format_amount(value: float, max_decimals: int = 8, min_decimals: int = 2) -> str:
    """
    Отформатировать сумму без лишних нулей в дробной части.
    """
    text = f"{value:.{max_decimals}f}".rstrip("0")
    integer_part, _, fraction = text.partition(".")
    fraction = fraction.ljust(min_decimals, "0")
    return f"{integer_part}.{fraction}"
