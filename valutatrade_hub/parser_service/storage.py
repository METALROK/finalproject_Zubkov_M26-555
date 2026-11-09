from typing import Any

from valutatrade_hub.core.utils import load_json, save_json, validate_currency_code
from valutatrade_hub.parser_service.config import ParserConfig

PAIRS_KEY = "pairs"
META_FIELDS = ("raw_id", "raw_rate", "request_ms", "status_code", "etag")


def normalize_snapshot(data: Any) -> dict[str, Any]:
    """
    Привести снимок rates.json к формату {"pairs": {...}, "last_refresh": ...}.

    Поддерживает и старый формат, где пары лежали в корне файла.
    """
    if not isinstance(data, dict):
        return {PAIRS_KEY: {}}
    pairs = data.get(PAIRS_KEY)
    if not isinstance(pairs, dict):
        pairs = {
            key: value
            for key, value in data.items()
            if isinstance(value, dict) and "rate" in value
        }
    snapshot: dict[str, Any] = {PAIRS_KEY: dict(pairs)}
    for key in ("source", "last_refresh"):
        if key in data:
            snapshot[key] = data[key]
    return snapshot

def make_history_record(
    from_code: str,
    to_code: str,
    rate: float,
    timestamp: str,
    source: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Запись истории.
    """
    for code in (from_code, to_code):
        if validate_currency_code(code) != code:
            raise ValueError(f"Код валюты '{code}' должен быть в верхнем регистре")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate <= 0:
        raise ValueError(f"Некорректный курс {from_code}_{to_code}: {rate!r}")
    return {
        "id": f"{from_code}_{to_code}_{timestamp}",
        "from_currency": from_code,
        "to_currency": to_code,
        "rate": float(rate),
        "timestamp": timestamp,
        "source": source,
        "meta": {
            key: (meta or {}).get(key) for key in META_FIELDS if key in (meta or {})
        },
    }


class RatesStorage:
    """
    Файлы Parser Service: снимок текущих курсов
    и журнал всех измерений. Запись атомарная.
    """

    def __init__(self, config: ParserConfig | None = None):
        self.config = config or ParserConfig()

    def load_snapshot(self) -> dict[str, Any]:
        """
        Текущий снимок rates.json.
        """
        return normalize_snapshot(load_json(self.config.RATES_FILE_PATH, {}))

    def save_snapshot(self, snapshot: dict[str, Any]):
        """
        Атомарно записать снимок rates.json.
        """
        save_json(self.config.RATES_FILE_PATH, snapshot)

    def load_history(self) -> list[dict[str, Any]]:
        """
        Все записи журнала exchange_rates.json.
        """
        data = load_json(self.config.HISTORY_FILE_PATH, [])
        return data if isinstance(data, list) else []

    def append_history(self, records: list[dict[str, Any]]) -> int:
        """
        Добавить новые записи в журнал.

        Возвращает количество добавленных записей.
        """
        history = self.load_history()
        known_ids = {item.get("id") for item in history if isinstance(item, dict)}
        new_records = [record for record in records if record["id"] not in known_ids]
        if new_records:
            history.extend(new_records)
            save_json(self.config.HISTORY_FILE_PATH, history)
        return len(new_records)
