import hmac
from datetime import datetime
from typing import Any

from valutatrade_hub.core.utils import generate_salt, hash_password

MIN_PASSWORD_LENGTH = 4


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
