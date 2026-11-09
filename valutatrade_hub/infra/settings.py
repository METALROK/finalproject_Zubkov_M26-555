import os
import sys
import threading
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

PYPROJECT_FILENAME = "pyproject.toml"
CONFIG_SECTION = "valutatrade"
ENV_PREFIX = "VALUTATRADE_"

DEFAULT_SETTINGS: dict[str, Any] = {
    "data_dir": "data",  # каталог с JSON-файлами
    "users_file": "users.json",  # пользователи
    "portfolios_file": "portfolios.json",  # портфели и кошельки
    "rates_file": "rates.json",  # кеш последних курсов
    "exchange_rates_file": "exchange_rates.json",  # история курсов (Parser Service)
    "rates_ttl_seconds": 300,  # сколько секунд курс считается свежим
    "default_base_currency": "USD",  # базовая валюта по умолчанию
    "log_dir": "logs",  # каталог логов
    "log_file": "actions.log",  # файл лога действий
    "parser_log_file": "parser.log",  # файл лога Parser Service
    "log_format": "string",  # формат логов: "string" или "json"
    "log_level": "INFO",  # уровень логирования
    "log_max_bytes": 1_048_576,  # размер файла лога до ротации
    "log_backup_count": 3,  # сколько старых файлов лога хранить
}

_MISSING = object()


class SettingsLoader:
    """
    Singleton: единая точка доступа к конфигурации проекта.
    """

    _instance: "SettingsLoader | None" = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._settings = {}
                    instance._project_root = Path.cwd()
                    instance.reload()
                    cls._instance = instance
        return cls._instance

    def get(self, key: str, default: Any = _MISSING) -> Any:
        """
        Вернуть значение параметра;.
        """
        if key in self._settings:
            return self._settings[key]
        if default is _MISSING:
            raise KeyError(f"Неизвестный ключ конфигурации '{key}'")
        return default

    def reload(self):
        """
        Перечитать конфигурацию из pyproject.toml и переменных окружения.
        """
        root = self._find_project_root()
        settings = dict(DEFAULT_SETTINGS)
        settings.update(self._read_pyproject_section(root / PYPROJECT_FILENAME))
        for key, value in settings.items():
            env_value = os.getenv(ENV_PREFIX + key.upper())
            if env_value is not None:
                settings[key] = self._cast(env_value, value)
        self._project_root = root
        self._settings = settings

    def as_dict(self) -> dict[str, Any]:
        """
        Копия всех параметров конфигурации.
        """
        return dict(self._settings)

    @property
    def project_root(self) -> Path:
        """
        Корень проекта: каталог с pyproject.toml.
        """
        return self._project_root

    def data_path(self, file_key: str) -> Path:
        """
        Полный путь к файлу данных.
        """
        return self._project_root / self.get("data_dir") / self.get(file_key)

    def log_path(self, file_key: str = "log_file") -> Path:
        """
        Полный путь к файлу лога (log_file или parser_log_file).
        """
        return self._project_root / self.get("log_dir") / self.get(file_key)

    @staticmethod
    def _find_project_root() -> Path:
        """
        Найти ближайший каталог с pyproject.toml, начиная с текущего.
        """
        cwd = Path.cwd()
        for directory in (cwd, *cwd.parents):
            if (directory / PYPROJECT_FILENAME).is_file():
                return directory
        return cwd

    @staticmethod
    def _read_pyproject_section(path: Path) -> dict[str, Any]:
        """
        Прочитать секцию tool.valutatrade.
        """
        if not path.is_file():
            return {}
        try:
            with path.open("rb") as file:
                data = tomllib.load(file)
        except (OSError, tomllib.TOMLDecodeError):
            return {}
        section = data.get("tool", {}).get(CONFIG_SECTION, {})
        return section if isinstance(section, dict) else {}

    @staticmethod
    def _cast(value: str, sample: Any) -> Any:
        """
        Привести строку из окружения к типу значения по умолчанию.
        """
        try:
            if isinstance(sample, int):
                return int(value)
            if isinstance(sample, float):
                return float(value)
        except ValueError:
            return sample
        return value
