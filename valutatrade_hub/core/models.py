import hmac
import math
from datetime import datetime
from typing import Any

from valutatrade_hub.core.utils import (
    format_amount,
    generate_salt,
    hash_password,
    validate_amount,
    validate_currency_code,
)

MIN_PASSWORD_LENGTH = 4
BASE_CURRENCY = "USD"

# Фиксированные курсы: сколько USD стоит 1 единица валюты.
EXCHANGE_RATES_TO_USD: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.0786,
    "GBP": 1.2591,
    "RUB": 0.01016,
    "BTC": 59337.21,
    "ETH": 3720.0,
}


class User:
    """
    Пользователь системы.
    """

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ):
        """
        Создать пользователя из уже подготовленных данных.
        """
        self.user_id = user_id
        self.username = username
        self._hashed_password = hashed_password
        self._salt = salt
        self.registration_date = registration_date

    @classmethod
    def create(cls, user_id: int, username: str, password: str) -> "User":
        """
        Создать нового пользователя: сгенерировать соль и захешировать пароль.
        """
        cls._validate_password(password)
        salt = generate_salt()
        return cls(
            user_id=user_id,
            username=username,
            hashed_password=hash_password(password, salt),
            salt=salt,
            registration_date=datetime.now().replace(microsecond=0),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "User":
        """
        Восстановить пользователя из словаря (формат users.json).
        """
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            hashed_password=data["hashed_password"],
            salt=data["salt"],
            registration_date=datetime.fromisoformat(data["registration_date"]),
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Сериализовать пользователя в словарь для записи в users.json.
        """
        return {
            "user_id": self._user_id,
            "username": self._username,
            "hashed_password": self._hashed_password,
            "salt": self._salt,
            "registration_date": self._registration_date.isoformat(),
        }

    @property
    def user_id(self) -> int:
        """
        Уникальный идентификатор пользователя.
        """
        return self._user_id

    @user_id.setter
    def user_id(self, value: int):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("user_id должен быть положительным целым числом")
        self._user_id = value

    @property
    def username(self) -> str:
        """
        Имя пользователя.
        """
        return self._username

    @username.setter
    def username(self, value: str):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя пользователя не может быть пустым")
        self._username = value.strip()

    @property
    def hashed_password(self) -> str:
        """
        Хеш пароля.
        """
        return self._hashed_password

    @property
    def salt(self) -> str:
        """
        Соль, использованная при хешировании пароля.
        """
        return self._salt

    @property
    def registration_date(self) -> datetime:
        """
        Дата и время регистрации.
        """
        return self._registration_date

    @registration_date.setter
    def registration_date(self, value: datetime):
        if not isinstance(value, datetime):
            raise TypeError("registration_date должен быть объектом datetime")
        self._registration_date = value

    def get_user_info(self) -> dict[str, Any]:
        """
        Вернуть публичную информацию о пользователе.
        """
        return {
            "user_id": self._user_id,
            "username": self._username,
            "registration_date": self._registration_date.isoformat(),
        }

    def change_password(self, new_password: str):
        """
        Сменить пароль: сгенерировать новую соль и сохранить новый хеш.
        """
        self._validate_password(new_password)
        self._salt = generate_salt()
        self._hashed_password = hash_password(new_password, self._salt)

    def verify_password(self, password: str) -> bool:
        """
        Проверить, совпадает ли введённый пароль с сохранённым.
        """
        if not isinstance(password, str):
            return False
        candidate = hash_password(password, self._salt)
        return hmac.compare_digest(candidate, self._hashed_password)

    @staticmethod
    def _validate_password(password: str):
        """
        Проверить пароль на минимальные требования.
        """
        if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(
                f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов"
            )

    def __repr__(self) -> str:
        return f"User(user_id={self._user_id}, username={self._username!r})"


class Wallet:
    """
    Кошелёк пользователя для одной конкретной валюты.
    """

    def __init__(self, currency_code: str, balance: float = 0.0):
        """
        Создать кошелёк для валюты с начальным балансом.
        """
        self._currency_code = validate_currency_code(currency_code)
        self.balance = balance

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Wallet":
        """
        Восстановить кошелёк из словаря (формат portfolios.json).
        """
        return cls(currency_code=data["currency_code"], balance=data["balance"])

    def to_dict(self) -> dict[str, Any]:
        """
        Сериализовать кошелёк в словарь для записи в portfolios.json.
        """
        return {"currency_code": self._currency_code, "balance": self._balance}

    @property
    def currency_code(self) -> str:
        """
        Код валюты кошелька.
        """
        return self._currency_code

    @property
    def balance(self) -> float:
        """
        Текущий баланс кошелька.
        """
        return self._balance

    @balance.setter
    def balance(self, value: float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Баланс должен быть числом")
        if not math.isfinite(value):
            raise ValueError("Баланс должен быть конечным числом")
        if value < 0:
            raise ValueError("Баланс не может быть отрицательным")
        self._balance = float(value)

    def deposit(self, amount: float):
        """
        Пополнить баланс на положительную сумму.
        """
        amount = validate_amount(amount)
        self.balance = self._balance + amount

    def withdraw(self, amount: float):
        """
        Снять положительную сумму, не превышающую текущий баланс.
        """
        amount = validate_amount(amount)
        if amount > self._balance:
            raise ValueError(
                f"Недостаточно средств: доступно "
                f"{format_amount(self._balance)} {self._currency_code}, "
                f"требуется {format_amount(amount)} {self._currency_code}"
            )
        self.balance = self._balance - amount

    def get_balance_info(self) -> str:
        """
        Вернуть строку с информацией о текущем балансе.
        """
        return f"{self._currency_code}: {format_amount(self._balance)}"

    def __repr__(self) -> str:
        return f"Wallet(currency_code={self._currency_code!r}, balance={self._balance})"


class Portfolio:
    """
    Портфель пользователя: набор кошельков в разных валютах.
    """

    def __init__(
        self,
        user_id: int,
        wallets: dict[str, Wallet] | None = None,
        user: User | None = None,
    ):
        """
        Создать портфель пользователя с набором кошельков.
        """
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id должен быть положительным целым числом")
        if user is not None and user.user_id != user_id:
            raise ValueError("user_id портфеля не совпадает с user_id пользователя")
        self._user_id = user_id
        self._user = user
        self._wallets: dict[str, Wallet] = {}
        for wallet in (wallets or {}).values():
            if not isinstance(wallet, Wallet):
                raise TypeError("Портфель может содержать только объекты Wallet")
            if wallet.currency_code in self._wallets:
                raise ValueError(f"Кошелёк {wallet.currency_code} уже есть в портфеле")
            self._wallets[wallet.currency_code] = wallet

    @classmethod
    def from_dict(cls, data: dict[str, Any], user: User | None = None) -> "Portfolio":
        """
        Восстановить портфель из словаря.
        """
        wallets = {
            code: Wallet(code, wallet_data["balance"])
            for code, wallet_data in data.get("wallets", {}).items()
        }
        return cls(user_id=data["user_id"], wallets=wallets, user=user)

    def to_dict(self) -> dict[str, Any]:
        """
        Сериализовать портфель в словарь для записи в portfolios.json.
        """
        return {
            "user_id": self._user_id,
            "wallets": {
                code: {"balance": wallet.balance}
                for code, wallet in self._wallets.items()
            },
        }

    @property
    def user_id(self) -> int:
        """
        Идентификатор владельца портфеля.
        """
        return self._user_id

    @property
    def user(self) -> User | None:
        """
        Владелец портфеля.
        """
        return self._user

    @property
    def wallets(self) -> dict[str, Wallet]:
        """
        Копия словаря кошельков: код валюты - Wallet.
        """
        return dict(self._wallets)

    def add_currency(self, currency_code: str) -> Wallet:
        """
        Добавить в портфель новый кошелёк с нулевым балансом.
        """
        code = validate_currency_code(currency_code)
        if code in self._wallets:
            raise ValueError(f"Кошелёк {code} уже есть в портфеле")
        wallet = Wallet(code)
        self._wallets[code] = wallet
        return wallet

    def get_wallet(self, currency_code: str) -> Wallet | None:
        """
        Вернуть кошелёк по коду валюты или None, если его нет.
        """
        code = validate_currency_code(currency_code)
        return self._wallets.get(code)

    def get_total_value(
        self,
        base_currency: str = BASE_CURRENCY,
        exchange_rates: dict[str, float] | None = None,
    ) -> float:
        """
        Посчитать общую стоимость всех кошельков в базовой валюте.

        exchange_rates - курсы валют к USD.
        """
        rates = exchange_rates if exchange_rates is not None else EXCHANGE_RATES_TO_USD
        base = validate_currency_code(base_currency)
        if base not in rates:
            raise ValueError(f"Неизвестна базовая валюта '{base}'")
        total_usd = 0.0
        for code, wallet in self._wallets.items():
            if code not in rates:
                raise ValueError(f"Курс для валюты '{code}' недоступен")
            total_usd += wallet.balance * rates[code]
        return total_usd / rates[base]

    def __repr__(self) -> str:
        codes = ", ".join(self._wallets)
        return f"Portfolio(user_id={self._user_id}, wallets=[{codes}])"
