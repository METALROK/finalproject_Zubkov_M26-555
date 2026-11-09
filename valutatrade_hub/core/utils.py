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
