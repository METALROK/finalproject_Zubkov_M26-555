import hashlib
import json
import math
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SALT_LENGTH_BYTES = 8
CURRENCY_CODE_MIN_LENGTH = 2
CURRENCY_CODE_MAX_LENGTH = 5
FIAT_DECIMALS = 2
CRYPTO_DECIMALS = 4


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

def validate_currency_code(code: str) -> str:
    """
    Проверить код валюты и вернуть его в верхнем регистре.
    """
    if not isinstance(code, str):
        raise TypeError("Код валюты должен быть строкой")
    code = code.strip().upper()
    if not (
        CURRENCY_CODE_MIN_LENGTH <= len(code) <= CURRENCY_CODE_MAX_LENGTH
        and code.isalnum()
    ):
        raise ValueError(
            f"Код валюты должен состоять из {CURRENCY_CODE_MIN_LENGTH}–"
            f"{CURRENCY_CODE_MAX_LENGTH} букв/цифр без пробелов"
        )
    return code

def validate_amount(amount: float) -> float:
    """
    Проверить, что сумма - положительное конечное число, и вернуть её как float.
    """
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise TypeError("Сумма должна быть числом")
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError("'amount' должен быть положительным числом")
    return float(amount)

def load_json(path: Path, default: Any) -> Any:
    """
    Прочитать JSON-файл; вернуть default, если файла нет или он пустой.
    """
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return default
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(f"Файл {path} повреждён: {error}") from error

def save_json(path: Path, data: Any):
    """
    Атомарно записать данные в JSON-файл.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
    os.replace(tmp_path, path)

def is_crypto_currency(code: str) -> bool:
    """
    Проверить по реестру валют, является ли валюта криптовалютой.
    """
    from valutatrade_hub.core.currencies import CryptoCurrency, get_currency
    from valutatrade_hub.core.exceptions import CurrencyNotFoundError

    try:
        return isinstance(get_currency(code), CryptoCurrency)
    except CurrencyNotFoundError:
        return False

def format_money(currency_code: str, value: float, thousands: bool = False) -> str:
    """
    Отформатировать сумму: 2 знака для фиата, 4-8 знаков для криптовалют.
    """
    if is_crypto_currency(currency_code):
        return format_amount(value, min_decimals=CRYPTO_DECIMALS)
    if thousands:
        return f"{value:,.{FIAT_DECIMALS}f}"
    return f"{value:.{FIAT_DECIMALS}f}"

def utc_iso(unix_seconds: float | None = None) -> str:
    """
    Время в ISO-формате UTC с суффиксом Z: 2025-10-10T12:00:00Z.
    """
    moment = (
        datetime.fromtimestamp(unix_seconds, tz=timezone.utc)
        if unix_seconds is not None
        else datetime.now(timezone.utc)
    )
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_iso_datetime(value: str | None) -> datetime | None:
    """
    Разобрать ISO-время.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
