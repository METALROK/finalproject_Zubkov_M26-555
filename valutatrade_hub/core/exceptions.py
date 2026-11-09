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
