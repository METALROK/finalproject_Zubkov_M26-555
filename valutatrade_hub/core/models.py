import hmac
import math
from datetime import datetime
from typing import Any

from valutatrade_hub.core.utils import (
    format_amount,
    generate_salt,
    hash_password,
)

MIN_PASSWORD_LENGTH = 4
CURRENCY_CODE_MIN_LENGTH = 2
CURRENCY_CODE_MAX_LENGTH = 5


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
    ) -> None:
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
    def user_id(self, value: int) -> None:
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
    def username(self, value: str) -> None:
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
    def registration_date(self, value: datetime) -> None:
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

    def change_password(self, new_password: str) -> None:
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
    def _validate_password(password: str) -> None:
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

    def __init__(self, currency_code: str, balance: float = 0.0) -> None:
        """
        Создать кошелёк для валюты с начальным балансом.
        """
        self._currency_code = self._normalize_currency_code(currency_code)
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
    def balance(self, value: float) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Баланс должен быть числом")
        if not math.isfinite(value):
            raise ValueError("Баланс должен быть конечным числом")
        if value < 0:
            raise ValueError("Баланс не может быть отрицательным")
        self._balance = float(value)

    def deposit(self, amount: float) -> None:
        """
        Пополнить баланс на положительную сумму.
        """
        amount = self._validate_amount(amount)
        self.balance = self._balance + amount

    def withdraw(self, amount: float) -> None:
        """
        Снять положительную сумму, не превышающую текущий баланс.
        """
        amount = self._validate_amount(amount)
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

    @staticmethod
    def _validate_amount(amount: float) -> float:
        """
        Проверить, что сумма операции - положительное конечное число.
        """
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise TypeError("Сумма должна быть числом")
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("'amount' должен быть положительным числом")
        return float(amount)

    @staticmethod
    def _normalize_currency_code(code: str) -> str:
        """
        Привести код валюты к верхнему регистру и проверить формат.
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

    def __repr__(self) -> str:
        return f"Wallet(currency_code={self._currency_code!r}, balance={self._balance})"
