import json
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader

ACTIONS_LOGGER_NAME = "valutatrade.actions"
PARSER_LOGGER_NAME = "valutatrade.parser"
LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"
STRING_LOG_FORMAT = "%(levelname)s %(asctime)s %(message)s"
LOG_FORMAT_STRING = "string"
LOG_FORMAT_JSON = "json"


class JsonFormatter(logging.Formatter):
    """
    Форматтер одной JSON-строки на запись.
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


def _file_handlers(logger: logging.Logger) -> list[logging.Handler]:
    return [h for h in logger.handlers if not isinstance(h, logging.NullHandler)]


def _build_file_handler(log_path: Path) -> RotatingFileHandler:
    """
    Файловый обработчик с ротацией и форматом из настроек.
    """
    settings = SettingsLoader()
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
    return handler


def setup_logging(force: bool = False) -> logging.Logger:
    """
    Настроить логгеры: действия -> log_file,
    Parser Service -> parser_log_file; ротация по размеру.
    """
    logger = logging.getLogger(ACTIONS_LOGGER_NAME)
    if _file_handlers(logger) and not force:
        return logger

    settings = SettingsLoader()
    level = str(settings.get("log_level")).upper()
    for name, file_key in (
        (ACTIONS_LOGGER_NAME, "log_file"),
        (PARSER_LOGGER_NAME, "parser_log_file"),
    ):
        handler = _build_file_handler(settings.log_path(file_key))
        named_logger = logging.getLogger(name)
        for old_handler in _file_handlers(named_logger):
            named_logger.removeHandler(old_handler)
            old_handler.close()
        named_logger.addHandler(handler)
        named_logger.setLevel(level)
        named_logger.propagate = False
    return logger
