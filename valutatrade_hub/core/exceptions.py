from valutatrade_hub.core.utils import format_money


class ValutaTradeError(Exception):
    """
    Базовое исключение предметной области ValutaTrade Hub.
    """


class CurrencyNotFoundError(ValutaTradeError):
    """
    Неизвестный код валюты.
    """

    def __init__(self, code: str):
        self.code = code
        super().__init__(f"Неизвестная валюта '{code}'")


class InsufficientFundsError(ValutaTradeError):
    """
    Недостаточно средств на кошельке для списания.

    Возникает в Wallet.withdraw().
    """

    def __init__(self, available: float, required: float, code: str):
        self.available = available
        self.required = required
        self.code = code
        super().__init__(
            f"Недостаточно средств: доступно {format_money(code, available)} {code}, "
            f"требуется {format_money(code, required)} {code}"
        )


class ApiRequestError(ValutaTradeError):
    """
    Сбой внешнего источника курсов.

    Возникает в слое получения курсов.
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Ошибка при обращении к внешнему API: {reason}")


class RateUnavailableError(ValutaTradeError):
    """
    Курс пары недоступен ни в кеше, ни у источника курсов.

    Возникает в usecases.get_rate() и при покупке/продаже.
    """

    def __init__(self, from_code: str, to_code: str, message: str | None = None):
        self.from_code = from_code
        self.to_code = to_code
        super().__init__(
            message
            or f"Курс {from_code}->{to_code} недоступен. Повторите попытку позже."
        )


class WalletNotFoundError(ValutaTradeError):
    """
    У пользователя нет кошелька в указанной валюте.

    Возникает в usecases.sell_currency().
    """

    def __init__(self, code: str):
        self.code = code
        super().__init__(
            f"У вас нет кошелька '{code}'. Добавьте валюту: "
            "она создаётся автоматически при первой покупке."
        )
