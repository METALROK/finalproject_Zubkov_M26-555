from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError
from valutatrade_hub.core.utils import validate_currency_code


class Currency(ABC):
    """
    Абстрактная валюта с единым интерфейсом для UI и логов.

    Инварианты:
    - code: верхний регистр, 2-5 символов, без пробелов.
    - name: непустая строка.
    """

    def __init__(self, name: str, code: str):
        self.name = name
        self.code = code

    @property
    def name(self) -> str:
        """
        Читаемое имя валюты.
        """
        return self._name

    @name.setter
    def name(self, value: str):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Название валюты не может быть пустым")
        self._name = value.strip()

    @property
    def code(self) -> str:
        """
        ISO-код или тикер валюты.
        """
        return self._code

    @code.setter
    def code(self, value: str):
        self._code = validate_currency_code(value)

    @abstractmethod
    def get_display_info(self) -> str:
        """
        Строковое представление валюты для UI и логов.
        """

    def __str__(self) -> str:
        return self.get_display_info()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self._code!r}, name={self._name!r})"


class FiatCurrency(Currency):
    """
    Фиатная валюта, выпускаемая государством или валютным союзом.
    """

    def __init__(self, name: str, code: str, issuing_country: str):
        super().__init__(name, code)
        self.issuing_country = issuing_country

    @property
    def issuing_country(self) -> str:
        """
        Страна или зона эмиссии.
        """
        return self._issuing_country

    @issuing_country.setter
    def issuing_country(self, value: str):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Страна эмиссии не может быть пустой")
        self._issuing_country = value.strip()

    def get_display_info(self) -> str:
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    """
    Криптовалюта с алгоритмом консенсуса и рыночной капитализацией.
    """

    def __init__(self, name: str, code: str, algorithm: str, market_cap: float):
        super().__init__(name, code)
        self.algorithm = algorithm
        self.market_cap = market_cap

    @property
    def algorithm(self) -> str:
        """
        Алгоритм хеширования/консенсуса.
        """
        return self._algorithm

    @algorithm.setter
    def algorithm(self, value: str):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Алгоритм криптовалюты не может быть пустым")
        self._algorithm = value.strip()

    @property
    def market_cap(self) -> float:
        """
        Последняя известная рыночная капитализация.
        """
        return self._market_cap

    @market_cap.setter
    def market_cap(self, value: float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Капитализация должна быть числом")
        if value < 0:
            raise ValueError("Капитализация не может быть отрицательной")
        self._market_cap = float(value)

    def get_display_info(self) -> str:
        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {format_market_cap(self.market_cap)})"
        )


def format_market_cap(value: float) -> str:
    """
    Краткая запись капитализации.
    """
    mantissa, exponent = f"{value:.2e}".split("e")
    return f"{mantissa}e{int(exponent)}"


_CURRENCY_REGISTRY: dict[str, Currency] = {
    currency.code: currency
    for currency in (
        FiatCurrency("US Dollar", "USD", "United States"),
        FiatCurrency("Euro", "EUR", "Eurozone"),
        FiatCurrency("British Pound", "GBP", "United Kingdom"),
        FiatCurrency("Russian Ruble", "RUB", "Russia"),
        CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12),
        CryptoCurrency("Ethereum", "ETH", "Ethash", 4.5e11),
    )
}


def get_currency(code: str) -> Currency:
    """
    Получить валюту из реестра по коду.

    Неизвестный или некорректный код выбрасывает CurrencyNotFoundError.
    """
    normalized = code.strip().upper() if isinstance(code, str) else str(code)
    currency = _CURRENCY_REGISTRY.get(normalized)
    if currency is None:
        raise CurrencyNotFoundError(normalized)
    return currency

def get_supported_codes() -> list[str]:
    """
    Список кодов всех валют из реестра.
    """
    return sorted(_CURRENCY_REGISTRY)
