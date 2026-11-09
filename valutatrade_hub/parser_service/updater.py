import logging
from collections.abc import Callable
from typing import Any

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.utils import utc_iso
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.logging_config import PARSER_LOGGER_NAME
from valutatrade_hub.parser_service.api_clients import (
    BaseApiClient,
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import (
    PAIRS_KEY,
    RatesStorage,
    make_history_record,
)

PARSER_SOURCE_NAME = "ParserService"

CLIENT_FACTORIES: dict[str, type[BaseApiClient]] = {
    "coingecko": CoinGeckoClient,
    "exchangerate": ExchangeRateApiClient,
}

ProgressCallback = Callable[[str, str], None]

logger = logging.getLogger(PARSER_LOGGER_NAME)
logger.addHandler(logging.NullHandler())


def create_clients(
    source: str | None = None, config: ParserConfig | None = None
) -> list[BaseApiClient]:
    """
    Клиенты API: все или только один источник.
    """
    config = config or ParserConfig()
    if source is None:
        return [factory(config) for factory in CLIENT_FACTORIES.values()]
    key = source.strip().lower()
    if key not in CLIENT_FACTORIES:
        available = ", ".join(CLIENT_FACTORIES)
        raise ValueError(f"Неизвестный источник '{source}'. Доступны: {available}")
    return [CLIENT_FACTORIES[key](config)]

def _short_reason(error: ApiRequestError, source: str) -> str:
    """
    Причина ошибки без повторного имени источника.
    """
    return error.reason.removeprefix(f"{source}: ")


class RatesUpdater:
    """
    Точка входа логики парсинга: опрашивает API-клиентов,
    объединяет курсы и сохраняет их через хранилище.
    """

    def __init__(
        self,
        clients: list[BaseApiClient] | None = None,
        storage: RatesStorage | None = None,
        config: ParserConfig | None = None,
        progress: ProgressCallback | None = None,
    ):
        self.config = config or ParserConfig()
        self.clients = (
            clients if clients is not None else create_clients(None, self.config)
        )
        self.storage = storage or RatesStorage(self.config)
        self.progress = progress

    def _report(self, level: int, message: str):
        """
        Записать шаг в parser.log и передать его в progress.
        """
        logger.log(level, message)
        if self.progress is not None:
            self.progress(logging.getLevelName(level), message)

    def _relative(self, path) -> str:
        try:
            return path.relative_to(SettingsLoader().project_root).as_posix()
        except ValueError:
            return str(path)

    def run_update(self) -> dict[str, Any]:
        """
        Обновить курсы от всех клиентов.
        """
        refreshed_at = utc_iso()
        self._report(logging.INFO, "Starting rates update...")

        pairs: dict[str, dict[str, Any]] = {}
        history: list[dict[str, Any]] = []
        updated: dict[str, int] = {}
        errors: dict[str, str] = {}

        for client in self.clients:
            source = client.source_name
            try:
                rates = client.fetch_rates()
            except ApiRequestError as error:
                errors[source] = _short_reason(error, source)
                self._report(
                    logging.ERROR, f"Failed to fetch from {source}: {errors[source]}"
                )
                continue
            except Exception as error:  # отказоустойчивость: не роняем остальных
                errors[source] = f"{type(error).__name__}: {error}"
                logger.exception("Unexpected error in %s", source)
                self._report(
                    logging.ERROR, f"Failed to fetch from {source}: {errors[source]}"
                )
                continue

            for pair, rate in rates.items():
                from_code, to_code = pair.split("_", 1)
                meta = client.last_meta.get(pair, {})
                pairs[pair] = {
                    "rate": rate,
                    "updated_at": refreshed_at,
                    "source": source,
                }
                history.append(
                    make_history_record(
                        from_code,
                        to_code,
                        rate,
                        meta.get("timestamp") or refreshed_at,
                        source,
                        meta,
                    )
                )
            updated[source] = len(rates)
            self._report(
                logging.INFO, f"Fetching from {source}... OK ({len(rates)} rates)"
            )

        if not pairs:
            self._report(logging.ERROR, "Update failed: no source returned rates")
            details = "; ".join(f"{s}: {r}" for s, r in errors.items())
            raise ApiRequestError(
                f"не удалось обновить курсы ({details or 'нет источников'})"
            )

        self._report(
            logging.INFO,
            f"Writing {len(pairs)} rates to "
            f"{self._relative(self.config.RATES_FILE_PATH)}...",
        )
        snapshot = self.storage.load_snapshot()
        snapshot[PAIRS_KEY].update(pairs)
        snapshot["source"] = PARSER_SOURCE_NAME
        snapshot["last_refresh"] = refreshed_at
        self.storage.save_snapshot(snapshot)
        history_added = self.storage.append_history(history)

        logger.info(
            "Update finished: updated=%d, total_in_cache=%d, history_added=%d, "
            "errors=%d",
            len(pairs),
            len(snapshot[PAIRS_KEY]),
            history_added,
            len(errors),
        )
        return {
            "last_refresh": refreshed_at,
            "updated": updated,
            "errors": errors,
            "pairs": pairs,
            "total_updated": len(pairs),
            "history_added": history_added,
            "total_pairs": len(snapshot[PAIRS_KEY]),
        }
