import copy
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from valutatrade_hub.core.utils import load_json, save_json
from valutatrade_hub.infra.settings import SettingsLoader


class DatabaseManager:
    """
    Singleton: абстракция над JSON-хранилищем.

    Пути к файлам берутся из SettingsLoader при каждом обращении,
    поэтому SettingsLoader().reload() сразу влияет на хранилище.
    Запись атомарная (временный файл -> переименование).
    Изменения данных - через transaction(): чтение -> модификация -> запись
    под блокировкой; при исключении файл не меняется.
    """

    _instance: "DatabaseManager | None" = None
    _lock = threading.Lock()
    _data_lock = threading.RLock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def _path(self, file_key: str) -> Path:
        return SettingsLoader().data_path(file_key)

    def read(self, file_key: str, default: Any) -> Any:
        """
        Прочитать JSON-файл по ключу конфигурации.
        """
        with self._data_lock:
            return load_json(self._path(file_key), copy.deepcopy(default))

    def write(self, file_key: str, data: Any):
        """
        Атомарно записать JSON-файл по ключу конфигурации.
        """
        with self._data_lock:
            save_json(self._path(file_key), data)

    @contextmanager
    def transaction(self, file_key: str, default: Any) -> Iterator[Any]:
        """
        Безопасное изменение файла: чтение -> модификация -> запись.

        Данные записываются только при успешном выходе из блока;
        если внутри возникло исключение, файл остаётся прежним.
        """
        with self._data_lock:
            data = self.read(file_key, default)
            yield data
            self.write(file_key, data)

    def load_users(self) -> list[dict[str, Any]]:
        """
        Список пользователей из users.json.
        """
        return self.read("users_file", [])

    def save_users(self, users: list[dict[str, Any]]):
        """
        Сохранить список пользователей в users.json.
        """
        self.write("users_file", users)

    def load_portfolios(self) -> list[dict[str, Any]]:
        """
        Список портфелей из portfolios.json.
        """
        return self.read("portfolios_file", [])

    def save_portfolios(self, portfolios: list[dict[str, Any]]):
        """
        Сохранить список портфелей в portfolios.json.
        """
        self.write("portfolios_file", portfolios)

    def load_rates(self) -> dict[str, Any]:
        """
        Кеш курсов из rates.json.
        """
        return self.read("rates_file", {})

    def save_rates(self, rates: dict[str, Any]):
        """
        Сохранить кеш курсов в rates.json.
        """
        self.write("rates_file", rates)
