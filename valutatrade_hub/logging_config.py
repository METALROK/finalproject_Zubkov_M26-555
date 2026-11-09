import json
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler

from valutatrade_hub.infra.settings import SettingsLoader

ACTIONS_LOGGER_NAME = "valutatrade.actions"
LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"
STRING_LOG_FORMAT = "%(levelname)s %(asctime)s %(message)s"
LOG_FORMAT_STRING = "string"
LOG_FORMAT_JSON = "json"


class JsonFormatter(logging.Formatter):
    """
    Форматтер одной JSON-строки на запись: timestamp, level, поля действия.
    """

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).isoformat(timespec="seconds")
        payload = {"timestamp": timestamp, "level": record.levelname}
        fields = getattr(record, "action_fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        else:
            payload["message"] = record.getMessage()
        return json.dumps(payload, ensure_ascii=False)

def setup_logging(force: bool = False) -> logging.Logger:
    """
    Настроить логгер действий: файл с ротацией по размеру, формат и уровень.

    Параметры берутся из SettingsLoader: log_dir, log_file, log_format
    ("string" или "json"), log_level (INFO по умолчанию, DEBUG для отладки),
    log_max_bytes и log_backup_count. Повторный вызов ничего не меняет,
    если не передан force=True.
    """
    logger = logging.getLogger(ACTIONS_LOGGER_NAME)
    if logger.handlers and not force:
        return logger
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    settings = SettingsLoader()
    log_path = settings.log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_path,
        maxBytes=settings.get("log_max_bytes"),
        backupCount=settings.get("log_backup_count"),
        encoding="utf-8",
    )
    if str(settings.get("log_format")).lower() == LOG_FORMAT_JSON:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(STRING_LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
        )

    logger.addHandler(handler)
    logger.setLevel(str(settings.get("log_level")).upper())
    logger.propagate = False
    return logger
