import logging
from typing import Any

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.utils import utc_iso
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

logger = logging.getLogger(PARSER_LOGGER_NAME)
logger.addHandler(logging.NullHandler())


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
    ):
        self.config = config or ParserConfig()
        if clients is None:
            clients = [
                CoinGeckoClient(self.config),
                ExchangeRateApiClient(self.config),
            ]
        self.clients = clients
        self.storage = storage or RatesStorage(self.config)

    def run_update(self) -> dict[str, Any]:
        """
        Обновить курсы от всех клиентов.
        """
        refreshed_at = utc_iso()
        logger.info("PARSER Старт обновления курсов (клиентов: %d)", len(self.clients))

        pairs: dict[str, dict[str, Any]] = {}
        history: list[dict[str, Any]] = []
        updated: dict[str, int] = {}
        errors: dict[str, str] = {}

        for client in self.clients:
            source = client.source_name
            try:
                rates = client.fetch_rates()
            except ApiRequestError as error:
                errors[source] = error.reason
                logger.error("PARSER %s: ошибка - %s", source, error)
                continue
            except Exception as error:  # отказоустойчивость: не роняем остальных
                errors[source] = f"{type(error).__name__}: {error}"
                logger.exception("PARSER %s: непредвиденная ошибка", source)
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
            logger.info(
                "PARSER %s: получено курсов %d (%s)",
                source,
                len(rates),
                ", ".join(sorted(rates)),
            )

        if not pairs:
            logger.error("PARSER Обновление не выполнено: ни один источник не ответил")
            details = "; ".join(errors.values()) or "нет настроенных источников"
            raise ApiRequestError(f"не удалось обновить курсы ({details})")

        snapshot = self.storage.load_snapshot()
        snapshot[PAIRS_KEY].update(pairs)
        snapshot["source"] = PARSER_SOURCE_NAME
        snapshot["last_refresh"] = refreshed_at
        self.storage.save_snapshot(snapshot)
        history_added = self.storage.append_history(history)

        logger.info(
            "PARSER Обновление завершено: пар обновлено %d, всего в кеше %d, "
            "новых записей в истории %d, ошибок %d",
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
            "history_added": history_added,
            "total_pairs": len(snapshot[PAIRS_KEY]),
        }
