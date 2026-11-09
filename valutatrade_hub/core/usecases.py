from datetime import datetime
from typing import Any

from valutatrade_hub.core.currencies import (
    Currency,
    get_currency,
    get_supported_codes,
)
from valutatrade_hub.core.exceptions import (
    InsufficientFundsError,
    RateUnavailableError,
    WalletNotFoundError,
)
from valutatrade_hub.core.models import (
    BASE_CURRENCY,
    EXCHANGE_RATES_TO_USD,
    Portfolio,
    User,
)
from valutatrade_hub.core.utils import (
    is_crypto_currency,
    parse_iso_datetime,
    utc_iso,
    validate_amount,
    validate_currency_code,
)
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.updater import (
    ProgressCallback,
    RatesUpdater,
    create_clients,
)

RATE_SOURCE_CACHE = "cache"
RATE_SOURCE_STUB = "stub"
EMPTY_CACHE_MESSAGE = (
    "Локальный кеш курсов пуст. Выполните 'update-rates', чтобы загрузить данные."
)

settings = SettingsLoader()
db = DatabaseManager()


def load_users() -> list[User]:
    """
    Загрузить всех пользователей из users.json.
    """
    return [User.from_dict(item) for item in db.load_users()]

def find_user_by_username(username: str) -> User | None:
    """
    Найти пользователя по имени.
    """
    target = username.strip().lower()
    for user in load_users():
        if user.username.lower() == target:
            return user
    return None

def load_portfolios() -> list[Portfolio]:
    """
    Загрузить все портфели из portfolios.json.
    """
    return [Portfolio.from_dict(item) for item in db.load_portfolios()]

def _find_portfolio(portfolios_data: list[dict], user_id: int) -> Portfolio:
    """
    Портфель пользователя из сырых данных portfolios.json (пустой, если нет).
    """
    for item in portfolios_data:
        if item.get("user_id") == user_id:
            return Portfolio.from_dict(item)
    return Portfolio(user_id)

def _store_portfolio(portfolios_data: list[dict], portfolio: Portfolio):
    """
    Заменить (или добавить) портфель в сырых данных portfolios.json.
    """
    portfolios_data[:] = [
        item for item in portfolios_data if item.get("user_id") != portfolio.user_id
    ]
    portfolios_data.append(portfolio.to_dict())
    portfolios_data.sort(key=lambda item: item["user_id"])

def load_rates_cache() -> dict[str, Any]:
    """
    Загрузить локальный кеш курсов из rates.json.
    """
    return db.load_rates()

def _cache_pairs(cache: dict[str, Any]) -> dict[str, Any]:
    """
    Пары курсов из rates.json.
    """
    pairs = cache.get("pairs")
    if isinstance(pairs, dict):
        return pairs
    return {key: value for key, value in cache.items() if isinstance(value, dict)}

def _read_pair(cache: dict[str, Any], from_code: str, to_code: str) -> dict | None:
    """
    Найти курс пары в кеше: прямой или обратный.
    """
    pairs = _cache_pairs(cache)
    direct = pairs.get(f"{from_code}_{to_code}")
    if isinstance(direct, dict) and "rate" in direct:
        return {"rate": float(direct["rate"]), "updated_at": direct.get("updated_at")}
    reverse = pairs.get(f"{to_code}_{from_code}")
    if isinstance(reverse, dict) and reverse.get("rate"):
        return {
            "rate": 1 / float(reverse["rate"]),
            "updated_at": reverse.get("updated_at"),
        }
    return None

def _rate_to_usd(code: str, cache: dict[str, Any]) -> tuple[float, str | None, str]:
    """
    Вернуть курс к USD, время обновления и источник для одной валюты.
    """
    if code == BASE_CURRENCY:
        return 1.0, None, RATE_SOURCE_CACHE
    pair = _read_pair(cache, code, BASE_CURRENCY)
    if pair is not None:
        return pair["rate"], pair["updated_at"], RATE_SOURCE_CACHE
    if code in EXCHANGE_RATES_TO_USD:
        return EXCHANGE_RATES_TO_USD[code], None, RATE_SOURCE_STUB
    raise ValueError(f"Курс для валюты '{code}' недоступен")

def _default_base() -> str:
    """
    Базовая валюта по умолчанию из настроек.
    """
    return settings.get("default_base_currency")

def _resolve_currency(code: str) -> str:
    """
    Проверить код по реестру валют; неизвестный код выбрасывает CurrencyNotFoundError.
    """
    return get_currency(code).code

def _now_iso() -> str:
    """
    Текущее время в ISO-формате с точностью до секунды.
    """
    return utc_iso()

def _is_fresh(updated_at: str | None, ttl_seconds: int | None = None) -> bool:
    """
    Проверить, что курс обновлялся не раньше, чем ttl_seconds назад.

    По умолчанию TTL берётся из настроек (rates_ttl_seconds).
    """
    if ttl_seconds is None:
        ttl_seconds = settings.get("rates_ttl_seconds")
    moment = parse_iso_datetime(updated_at)
    if moment is None:
        return False
    now = datetime.now(moment.tzinfo) if moment.tzinfo else datetime.now()
    return (now - moment).total_seconds() <= ttl_seconds

def refresh_rates_cache() -> dict[str, Any]:
    """
    Обновить кеш rates.json через Parser Service и вернуть его.

    Если ни один источник курсов не ответил -> ApiRequestError.
    """
    RatesUpdater().run_update()
    return load_rates_cache()

def _compute_rate(from_code: str, to_code: str, cache: dict[str, Any]) -> dict:
    """
    Посчитать курс FROM -> TO по кешу.
    """
    result: dict[str, Any] = {"from": from_code, "to": to_code}
    pair = _read_pair(cache, from_code, to_code)
    if pair is not None:
        return result | pair | {"source": RATE_SOURCE_CACHE}

    from_usd, from_time, from_source = _rate_to_usd(from_code, cache)
    to_usd, to_time, to_source = _rate_to_usd(to_code, cache)
    times = [time for time in (from_time, to_time) if time]
    is_stub = RATE_SOURCE_STUB in (from_source, to_source)
    return result | {
        "rate": from_usd / to_usd,
        "updated_at": min(times) if times and not is_stub else None,
        "source": RATE_SOURCE_STUB if is_stub else RATE_SOURCE_CACHE,
    }

def get_rate(from_currency: str, to_currency: str) -> dict[str, Any]:
    """
    Единый контракт получения курса FROM -> TO.

    Коды проверяются по реестру валют (иначе CurrencyNotFoundError).
    Курс берётся из кеша rates.json, если он моложе TTL (rates_ttl_seconds
    из SettingsLoader); иначе кеш обновляется - при сбое источника
    пробрасывается ApiRequestError. Курса нет и после обновления ->
    RateUnavailableError. Возвращает словарь: from, to, rate, updated_at, source.
    """
    from_code = _resolve_currency(from_currency)
    to_code = _resolve_currency(to_currency)
    if from_code == to_code:
        return {
            "from": from_code,
            "to": to_code,
            "rate": 1.0,
            "updated_at": _now_iso(),
            "source": "fixed",
        }

    try:
        cached = _compute_rate(from_code, to_code, load_rates_cache())
        if cached["source"] == RATE_SOURCE_CACHE and _is_fresh(cached["updated_at"]):
            return cached
    except ValueError:
        pass

    cache = refresh_rates_cache()
    try:
        return _compute_rate(from_code, to_code, cache)
    except ValueError as error:
        raise RateUnavailableError(from_code, to_code) from error

def get_rates_to_usd() -> dict[str, float]:
    """
    Курсы всех известных валют к USD.
    """
    cache = load_rates_cache()
    codes = set(EXCHANGE_RATES_TO_USD)
    for key in _cache_pairs(cache):
        if "_" in key:
            codes.update(key.split("_", 1))
    rates = {}
    for code in codes:
        try:
            rates[code] = _rate_to_usd(code, cache)[0]
        except ValueError:
            continue
    return rates

def _next_user_id(users: list[User]) -> int:
    """
    Сгенерировать следующий user_id.
    """
    return max((user.user_id for user in users), default=0) + 1

@log_action("REGISTER")
def register_user(username: str, password: str) -> User:
    """
    Зарегистрировать пользователя и создать для него пустой портфель.
    """
    with db.transaction("users_file", []) as users_data:
        users = [User.from_dict(item) for item in users_data]
        target = username.strip().lower()
        if any(user.username.lower() == target for user in users):
            raise ValueError(f"Имя пользователя '{username.strip()}' уже занято")
        user = User.create(_next_user_id(users), username, password)
        users_data.append(user.to_dict())

    with db.transaction("portfolios_file", []) as portfolios_data:
        _store_portfolio(portfolios_data, Portfolio(user.user_id))
    return user

@log_action("LOGIN")
def login_user(username: str, password: str) -> User:
    """
    Проверить имя и пароль; вернуть пользователя при успешном входе.
    """
    user = find_user_by_username(username)
    if user is None:
        raise ValueError(f"Пользователь '{username.strip()}' не найден")
    if not user.verify_password(password):
        raise ValueError("Неверный пароль")
    return user

def get_portfolio(user_id: int) -> Portfolio:
    """
    Вернуть портфель пользователя.
    """
    return _find_portfolio(db.load_portfolios(), user_id)

def get_portfolio_summary(
    user_id: int, base_currency: str | None = None
) -> dict[str, Any]:
    """
    Сводка по портфелю: балансы кошельков и их стоимость в базовой валюте.
    """
    base = validate_currency_code(base_currency or _default_base())
    rates = get_rates_to_usd()
    if base not in rates:
        raise ValueError(f"Неизвестная базовая валюта '{base}'")

    portfolio = get_portfolio(user_id)
    wallets = []
    for code, wallet in portfolio.wallets.items():
        if code not in rates:
            raise ValueError(f"Курс для валюты '{code}' недоступен")
        wallets.append(
            {
                "currency_code": code,
                "balance": wallet.balance,
                "value": wallet.balance * rates[code] / rates[base],
            }
        )
    total = portfolio.get_total_value(base, exchange_rates=rates)
    return {"base": base, "wallets": wallets, "total": total}

def save_portfolio(portfolio: Portfolio):
    """
    Сохранить один портфель, заменив его прежнюю версию в portfolios.json.
    """
    with db.transaction("portfolios_file", []) as portfolios_data:
        _store_portfolio(portfolios_data, portfolio)

def _get_rate_to_base(currency_code: str, base_currency: str) -> float:
    """
    Получить курс валюты к базовой или сообщить, что курс недоступен.
    """
    try:
        return get_rate(currency_code, base_currency)["rate"]
    except RateUnavailableError as error:
        raise RateUnavailableError(
            currency_code,
            base_currency,
            f"Не удалось получить курс для {currency_code}->{base_currency}",
        ) from error

@log_action("BUY", verbose=True)
def buy_currency(
    user_id: int, currency_code: str, amount: float, base_currency: str | None = None
) -> dict[str, Any]:
    """
    Купить amount единиц валюты: пополнить или создать кошелёк.

    Ошибки: ValueError (amount), CurrencyNotFoundError (код валюты),
    ApiRequestError/RateUnavailableError (курс).
    """
    amount = validate_amount(amount)
    code = _resolve_currency(currency_code)
    base = _resolve_currency(base_currency or _default_base())
    rate = _get_rate_to_base(code, base)

    with db.transaction("portfolios_file", []) as portfolios_data:
        portfolio = _find_portfolio(portfolios_data, user_id)
        wallet = portfolio.get_wallet(code) or portfolio.add_currency(code)
        old_balance = wallet.balance
        wallet.deposit(amount)
        _store_portfolio(portfolios_data, portfolio)

    return {
        "currency_code": code,
        "amount": amount,
        "old_balance": old_balance,
        "new_balance": wallet.balance,
        "rate": rate,
        "base": base,
        "cost": amount * rate,
        "currency_info": get_currency(code).get_display_info(),
    }

@log_action("SELL", verbose=True)
def sell_currency(
    user_id: int, currency_code: str, amount: float, base_currency: str | None = None
) -> dict[str, Any]:
    """
    Продать amount единиц валюты.

    Если у пользователя есть кошелёк базовой валюты, выручка зачисляется на него.
    Возвращает словарь: currency_code, amount, old_balance, new_balance,
    rate, base, revenue, base_old_balance/base_new_balance (None без зачисления).
    Ошибки: ValueError (amount), CurrencyNotFoundError, WalletNotFoundError,
    InsufficientFundsError, ApiRequestError/RateUnavailableError (курс).
    """
    amount = validate_amount(amount)
    code = _resolve_currency(currency_code)
    base = _resolve_currency(base_currency or _default_base())

    with db.transaction("portfolios_file", []) as portfolios_data:
        portfolio = _find_portfolio(portfolios_data, user_id)
        wallet = portfolio.get_wallet(code)
        if wallet is None:
            raise WalletNotFoundError(code)
        if amount > wallet.balance:
            raise InsufficientFundsError(wallet.balance, amount, code)

        rate = _get_rate_to_base(code, base)
        old_balance = wallet.balance
        wallet.withdraw(amount)
        revenue = amount * rate

        base_wallet = portfolio.get_wallet(base) if code != base else None
        base_old_balance = base_new_balance = None
        if base_wallet is not None:
            base_old_balance = base_wallet.balance
            base_wallet.deposit(revenue)
            base_new_balance = base_wallet.balance
        _store_portfolio(portfolios_data, portfolio)

    return {
        "currency_code": code,
        "amount": amount,
        "old_balance": old_balance,
        "new_balance": wallet.balance,
        "rate": rate,
        "base": base,
        "revenue": revenue,
        "currency_info": get_currency(code).get_display_info(),
        "base_old_balance": base_old_balance,
        "base_new_balance": base_new_balance,
    }

def list_currencies() -> list[Currency]:
    """
    Все валюты из реестра, отсортированные по коду.
    """
    return [get_currency(code) for code in get_supported_codes()]

def update_rates(
    source: str | None = None, progress: ProgressCallback | None = None
) -> dict[str, Any]:
    """
    Немедленно обновить курсы через Parser Service.
    """
    updater = RatesUpdater(clients=create_clients(source), progress=progress)
    return updater.run_update()

def _cached_rows(cache: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Корректные пары из кеша в виде строк.
    """
    rows = []
    for pair, value in _cache_pairs(cache).items():
        if "_" not in pair or not isinstance(value, dict):
            continue
        rate = value.get("rate")
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate <= 0:
            continue
        from_code, to_code = pair.split("_", 1)
        rows.append(
            {
                "pair": pair,
                "from": from_code,
                "to": to_code,
                "rate": float(rate),
                "updated_at": value.get("updated_at"),
                "source": value.get("source"),
            }
        )
    return rows

def _rebase_rows(rows: list[dict[str, Any]], base: str) -> list[dict[str, Any]]:
    """
    Пересчитать курсы X_USD в X_<base> через курс базы к USD из кеша.
    """
    usd_rates = {row["from"]: row for row in rows if row["to"] == BASE_CURRENCY}
    if base == BASE_CURRENCY:
        return list(usd_rates.values())
    base_row = usd_rates.get(base)
    if base_row is None:
        raise ValueError(f"Курс для '{base}' не найден в кеше.")
    rebased = [
        {
            "pair": f"{BASE_CURRENCY}_{base}",
            "from": BASE_CURRENCY,
            "to": base,
            "rate": 1 / base_row["rate"],
            "updated_at": base_row["updated_at"],
            "source": base_row["source"],
        }
    ]
    for code, row in usd_rates.items():
        if code == base:
            continue
        rebased.append(
            row
            | {
                "pair": f"{code}_{base}",
                "to": base,
                "rate": row["rate"] / base_row["rate"],
                "updated_at": min(
                    filter(None, (row["updated_at"], base_row["updated_at"])),
                    default=None,
                ),
            }
        )
    return rebased

def get_cached_rates(
    currency: str | None = None, top: int | None = None, base: str | None = None
) -> dict[str, Any]:
    """
    Курсы из локального кеша rates.json.
    """
    cache = load_rates_cache()
    rows = _cached_rows(cache)
    if not rows:
        raise ValueError(EMPTY_CACHE_MESSAGE)

    base_code = None
    if base:
        base_code = _resolve_currency(base)
        rows = _rebase_rows(rows, base_code)

    if currency:
        code = currency.strip().upper()
        rows = [row for row in rows if row["from"] == code]
        if not rows:
            raise ValueError(f"Курс для '{code}' не найден в кеше.")

    if top is not None:
        if isinstance(top, bool) or not isinstance(top, int) or top <= 0:
            raise ValueError("'top' должен быть положительным целым числом")
        rows = [row for row in rows if is_crypto_currency(row["from"])]
        if not rows:
            raise ValueError("В кеше нет курсов криптовалют.")
        rows = sorted(rows, key=lambda row: row["rate"], reverse=True)[:top]
    else:
        rows = sorted(rows, key=lambda row: row["pair"])

    times = [row["updated_at"] for row in rows if row["updated_at"]]
    return {
        "last_refresh": cache.get("last_refresh") or max(times, default=None),
        "base": base_code,
        "rows": rows,
    }
