import os
from dataclasses import dataclass, field
from pathlib import Path

from valutatrade_hub.core.utils import validate_currency_code
from valutatrade_hub.infra.settings import SettingsLoader

ENV_FILE_NAME = ".env"
EXCHANGERATE_API_KEY_ENV = "EXCHANGERATE_API_KEY"

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
EXCHANGERATE_API_URL = "https://v6.exchangerate-api.com/v6"

BASE_CURRENCY = "USD"
FIAT_CURRENCIES = ("EUR", "GBP", "RUB")
CRYPTO_CURRENCIES = ("BTC", "ETH", "SOL")
CRYPTO_ID_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
}

REQUEST_TIMEOUT = 10

COINGECKO_SOURCE = "CoinGecko"
EXCHANGERATE_SOURCE = "ExchangeRate-API"


def load_env_file(path: Path) -> None:
    """
    Загрузить переменные KEY=VALUE из файла .env в os.environ.

    Уже заданные переменные окружения не перезаписываются.
    Файл .env не хранится в git (см. .gitignore).
    """
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def _read_api_key() -> str | None:
    """
    Ключ ExchangeRate-API: из окружения или из файла .env в корне проекта.
    """
    load_env_file(SettingsLoader().project_root / ENV_FILE_NAME)
    key = os.getenv(EXCHANGERATE_API_KEY_ENV, "").strip()
    return key or None


def _rates_file_path() -> Path:
    return SettingsLoader().data_path("rates_file")


def _history_file_path() -> Path:
    return SettingsLoader().data_path("exchange_rates_file")


@dataclass(frozen=True)
class ParserConfig:
    """
    Настройки Parser Service: ключи, эндпоинты, валюты, таймаут, пути.

    Ключ EXCHANGERATE_API_KEY читается из переменной окружения
    (или из не отслеживаемого git-ом файла .env) при создании объекта
    и не выводится в repr.
    """

    EXCHANGERATE_API_KEY: str | None = field(default_factory=_read_api_key, repr=False)

    # Эндпоинты
    COINGECKO_URL: str = COINGECKO_URL
    EXCHANGERATE_API_URL: str = EXCHANGERATE_API_URL

    # Валюты
    BASE_CURRENCY: str = BASE_CURRENCY
    FIAT_CURRENCIES: tuple[str, ...] = FIAT_CURRENCIES
    CRYPTO_CURRENCIES: tuple[str, ...] = CRYPTO_CURRENCIES
    CRYPTO_ID_MAP: dict[str, str] = field(default_factory=lambda: dict(CRYPTO_ID_MAP))

    # Пути (из SettingsLoader: data_dir + rates_file / exchange_rates_file)
    RATES_FILE_PATH: Path = field(default_factory=_rates_file_path)
    HISTORY_FILE_PATH: Path = field(default_factory=_history_file_path)

    # Сетевые параметры
    REQUEST_TIMEOUT: int = REQUEST_TIMEOUT

    def __post_init__(self):
        """
        Проверить согласованность настроек: формат кодов и CRYPTO_ID_MAP.
        """
        codes = (self.BASE_CURRENCY, *self.FIAT_CURRENCIES, *self.CRYPTO_CURRENCIES)
        for code in codes:
            if validate_currency_code(code) != code:
                raise ValueError(f"Код валюты '{code}' должен быть в верхнем регистре")
        missing = [
            code for code in self.CRYPTO_CURRENCIES if code not in self.CRYPTO_ID_MAP
        ]
        if missing:
            raise ValueError(f"Нет ID CoinGecko для валют: {', '.join(missing)}")
        if self.REQUEST_TIMEOUT <= 0:
            raise ValueError("REQUEST_TIMEOUT должен быть положительным")

    @property
    def has_exchangerate_key(self) -> bool:
        """
        Задан ли ключ ExchangeRate-API.
        """
        return bool(self.EXCHANGERATE_API_KEY)

    def coingecko_ids(self) -> list[str]:
        """
        ID CoinGecko для отслеживаемых криптовалют (bitcoin, ethereum, ...).
        """
        return [self.CRYPTO_ID_MAP[code] for code in self.CRYPTO_CURRENCIES]

    def exchangerate_latest_url(self) -> str:
        """
        URL запроса последних курсов фиата: .../v6/<KEY>/latest/<BASE>.
        """
        if not self.EXCHANGERATE_API_KEY:
            raise ValueError(
                f"Не задан ключ ExchangeRate-API: укажите {EXCHANGERATE_API_KEY_ENV} "
                f"в переменных окружения или в файле {ENV_FILE_NAME}"
            )
        return (
            f"{self.EXCHANGERATE_API_URL}/{self.EXCHANGERATE_API_KEY}"
            f"/latest/{self.BASE_CURRENCY}"
        )
