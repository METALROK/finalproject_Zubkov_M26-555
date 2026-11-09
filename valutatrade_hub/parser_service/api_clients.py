import logging
import time
from abc import ABC, abstractmethod
from typing import Any

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.utils import utc_iso
from valutatrade_hub.logging_config import PARSER_LOGGER_NAME
from valutatrade_hub.parser_service.config import (
    COINGECKO_SOURCE,
    EXCHANGERATE_API_KEY_ENV,
    EXCHANGERATE_SOURCE,
    ParserConfig,
)

RATE_PRECISION = 10
HTTP_OK = 200

HTTP_ERROR_MESSAGES = {
    400: "некорректный запрос (400 Bad Request)",
    401: "неверный или отсутствующий API-ключ (401 Unauthorized)",
    403: "доступ запрещён: проверьте API-ключ (403 Forbidden)",
    404: "ресурс не найден (404 Not Found)",
    429: "превышен лимит запросов (429 Too Many Requests), подождите",
}

EXCHANGERATE_ERROR_MESSAGES = {
    "invalid-key": "неверный API-ключ",
    "inactive-account": "аккаунт не активирован (подтвердите email)",
    "quota-reached": "исчерпан лимит запросов тарифа",
    "unsupported-code": "неподдерживаемый код валюты",
    "malformed-request": "некорректный запрос",
}

logger = logging.getLogger(PARSER_LOGGER_NAME)
logger.addHandler(logging.NullHandler())


def _is_valid_rate(value: Any) -> bool:
    """
    Курс - положительное число.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


class BaseApiClient(ABC):
    """
    Единый интерфейс клиента внешнего API курсов.
    """

    source_name: str = "API"

    def __init__(
        self,
        config: ParserConfig | None = None,
        session: requests.Session | None = None,
    ):
        self.config = config or ParserConfig()
        self.session = session or requests.Session()
        self.last_meta: dict[str, dict[str, Any]] = {}

    @abstractmethod
    def fetch_rates(self) -> dict[str, float]:
        """
        Получить актуальные курсы в формате словаря.
        """

    def _request_json(
        self, url: str, params: dict[str, Any] | None = None
    ) -> tuple[Any, dict[str, Any]]:
        """
        GET-запрос с таймаутом: проверить status_code и разобрать JSON.
        """
        started = time.perf_counter()
        try:
            response = self.session.get(
                url, params=params, timeout=self.config.REQUEST_TIMEOUT
            )
        except requests.exceptions.Timeout as error:
            raise ApiRequestError(
                f"{self.source_name}: превышено время ожидания "
                f"({self.config.REQUEST_TIMEOUT} с)"
            ) from error
        except requests.exceptions.ConnectionError as error:
            raise ApiRequestError(
                f"{self.source_name}: нет соединения с сервером"
            ) from error
        except requests.exceptions.RequestException as error:
            raise ApiRequestError(
                f"{self.source_name}: {type(error).__name__}"
            ) from error

        meta = {
            "request_ms": round((time.perf_counter() - started) * 1000),
            "status_code": response.status_code,
            "etag": response.headers.get("ETag"),
        }
        logger.debug(
            "%s: HTTP %s за %s мс",
            self.source_name,
            meta["status_code"],
            meta["request_ms"],
        )

        if response.status_code != HTTP_OK:
            raise ApiRequestError(
                f"{self.source_name}: {self._describe_http_error(response)}"
            )
        try:
            return response.json(), meta
        except ValueError as error:
            raise ApiRequestError(
                f"{self.source_name}: некорректный ответ (не JSON)"
            ) from error

    def _describe_http_error(self, response: requests.Response) -> str:
        """
        Понятное описание HTTP-ошибки по коду ответа.
        """
        code = response.status_code
        if code in HTTP_ERROR_MESSAGES:
            return HTTP_ERROR_MESSAGES[code]
        if code >= 500:
            return f"сервис временно недоступен ({code})"
        return f"неожиданный ответ сервера ({code})"


class CoinGeckoClient(BaseApiClient):
    """
    Курсы криптовалют из CoinGecko.
    """

    source_name = COINGECKO_SOURCE

    def fetch_rates(self) -> dict[str, float]:
        base = self.config.BASE_CURRENCY
        vs_currency = base.lower()
        params = {
            "ids": ",".join(self.config.coingecko_ids()),
            "vs_currencies": vs_currency,
            "include_last_updated_at": "true",
        }
        data, meta = self._request_json(self.config.COINGECKO_URL, params)
        if not isinstance(data, dict):
            raise ApiRequestError(f"{self.source_name}: неожиданный формат ответа")

        rates: dict[str, float] = {}
        self.last_meta = {}
        for code in self.config.CRYPTO_CURRENCIES:
            raw_id = self.config.CRYPTO_ID_MAP[code]
            entry = data.get(raw_id)
            rate = entry.get(vs_currency) if isinstance(entry, dict) else None
            if not _is_valid_rate(rate):
                logger.warning("%s: нет корректного курса для %s", raw_id, code)
                continue
            pair = f"{code}_{base}"
            rates[pair] = float(rate)
            updated = entry.get("last_updated_at")
            self.last_meta[pair] = meta | {
                "raw_id": raw_id,
                "timestamp": utc_iso(updated if _is_valid_rate(updated) else None),
            }

        if not rates:
            raise ApiRequestError(f"{self.source_name}: в ответе нет курсов")
        return rates


class ExchangeRateApiClient(BaseApiClient):
    """
    Курсы фиатных валют из ExchangeRate-API.
    """

    source_name = EXCHANGERATE_SOURCE

    def fetch_rates(self) -> dict[str, float]:
        if not self.config.has_exchangerate_key:
            raise ApiRequestError(
                f"{self.source_name}: не задан API-ключ "
                f"(переменная {EXCHANGERATE_API_KEY_ENV} или файл .env)"
            )
        data, meta = self._request_json(self.config.exchangerate_latest_url())
        if not isinstance(data, dict):
            raise ApiRequestError(f"{self.source_name}: неожиданный формат ответа")
        if data.get("result") != "success":
            raise ApiRequestError(
                f"{self.source_name}: {self._describe_api_error(data)}"
            )

        api_rates = data.get("rates")
        if not isinstance(api_rates, dict):
            raise ApiRequestError(f"{self.source_name}: в ответе нет поля 'rates'")

        base = self.config.BASE_CURRENCY
        updated = data.get("time_last_update_unix")
        timestamp = utc_iso(updated if _is_valid_rate(updated) else None)
        rates: dict[str, float] = {}
        self.last_meta = {}
        for code in self.config.FIAT_CURRENCIES:
            base_to_code = api_rates.get(code)
            if not _is_valid_rate(base_to_code):
                logger.warning("%s: нет корректного курса для %s", base, code)
                continue
            pair = f"{code}_{base}"
            rates[pair] = round(1 / float(base_to_code), RATE_PRECISION)
            self.last_meta[pair] = meta | {
                "raw_id": code,
                "raw_rate": base_to_code,
                "timestamp": timestamp,
            }

        if not rates:
            raise ApiRequestError(f"{self.source_name}: в ответе нет курсов")
        return rates

    def _describe_http_error(self, response: requests.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            data = None
        if isinstance(data, dict) and data.get("result") == "error":
            return self._describe_api_error(data)
        return super()._describe_http_error(response)

    @staticmethod
    def _describe_api_error(data: dict[str, Any]) -> str:
        error_type = str(data.get("error-type", "unknown"))
        return EXCHANGERATE_ERROR_MESSAGES.get(error_type, f"ошибка API ({error_type})")
