import functools
import inspect
import logging
from collections.abc import Callable
from typing import Any

from valutatrade_hub.core.utils import format_amount, format_money
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.logging_config import ACTIONS_LOGGER_NAME

RESULT_OK = "OK"
RESULT_ERROR = "ERROR"

FIELD_ORDER = (
    "action",
    "user",
    "user_id",
    "currency",
    "amount",
    "rate",
    "base",
    "before",
    "after",
    "result",
    "error_type",
    "error_message",
)

logger = logging.getLogger(ACTIONS_LOGGER_NAME)


def _find_username(user_id: Any) -> str | None:
    """
    Найти имя пользователя по user_id .
    """
    try:
        for user in DatabaseManager().load_users():
            if user.get("user_id") == user_id:
                return user.get("username")
    except Exception:
        return None
    return None

def _fields_from_args(action: str, call_args: dict[str, Any]) -> dict[str, Any]:
    """
    Поля лога из аргументов вызова.
    """
    fields: dict[str, Any] = {"action": action}
    if "username" in call_args:
        fields["user"] = str(call_args["username"]).strip()
    if "user_id" in call_args:
        fields["user_id"] = call_args["user_id"]
        username = _find_username(call_args["user_id"])
        if username:
            fields["user"] = username
    if "currency_code" in call_args:
        fields["currency"] = str(call_args["currency_code"]).strip().upper()
    if "amount" in call_args:
        fields["amount"] = call_args["amount"]
    return fields

def _fields_from_result(result: Any, verbose: bool) -> dict[str, Any]:
    """
    Поля лога из результата usecase.
    """
    fields: dict[str, Any] = {}
    if isinstance(result, dict):
        for source_key, field in (
            ("currency_code", "currency"),
            ("amount", "amount"),
            ("rate", "rate"),
            ("base", "base"),
        ):
            if source_key in result:
                fields[field] = result[source_key]
        if verbose and "old_balance" in result and "new_balance" in result:
            fields["before"] = result["old_balance"]
            fields["after"] = result["new_balance"]
    elif hasattr(result, "user_id") and hasattr(result, "username"):
        fields["user"] = result.username
        fields["user_id"] = result.user_id
    return fields

def _format_value(key: str, value: Any, fields: dict[str, Any]) -> str:
    """
    Отформатировать значение поля для строкового лога.
    """
    if isinstance(value, bool) or value is None or key == "result":
        return str(value)
    if key in ("amount", "before", "after") and isinstance(value, (int, float)):
        return format_money(str(fields.get("currency", "")), value)
    if key == "rate" and isinstance(value, (int, float)):
        return format_amount(value)
    if isinstance(value, (int, float)):
        return str(value)
    return repr(str(value))

def render_fields(fields: dict[str, Any]) -> str:
    parts = [str(fields["action"])]
    for key in FIELD_ORDER[1:]:
        if key in fields:
            parts.append(f"{key}={_format_value(key, fields[key], fields)}")
    return " ".join(parts)

def _emit(fields: dict[str, Any]):
    logger.info(render_fields(fields), extra={"action_fields": fields})

def log_action(action: str, verbose: bool = False) -> Callable:
    """
    Декоратор: логировать доменную операцию на уровне INFO.

    Пишет action, user/user_id, currency, amount, rate и base (если есть),
    result=OK/ERROR, а при исключении - error_type и error_message.
    verbose=True добавляет состояние кошелька before/after.
    Исключения не пропадают: после записи в лог пробрасываются дальше.
    """

    def decorator(func: Callable) -> Callable:
        signature = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                call_args = dict(signature.bind_partial(*args, **kwargs).arguments)
            except TypeError:
                call_args = {}
            fields = _fields_from_args(action, call_args)
            logger.debug("%s started", action)
            try:
                result = func(*args, **kwargs)
            except Exception as error:
                fields.update(
                    result=RESULT_ERROR,
                    error_type=type(error).__name__,
                    error_message=str(error),
                )
                _emit(fields)
                raise
            fields.update(_fields_from_result(result, verbose))
            fields["result"] = RESULT_OK
            _emit(fields)
            return result

        return wrapper

    return decorator
