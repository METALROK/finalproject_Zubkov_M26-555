from datetime import datetime
from typing import Any

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import ApiRequestError, RateUnavailableError
from valutatrade_hub.core.models import (
    BASE_CURRENCY,
    EXCHANGE_RATES_TO_USD,
    Portfolio,
    User,
)
from valutatrade_hub.core.utils import (
    PORTFOLIOS_FILE,
    RATES_FILE,
    USERS_FILE,
    load_json,
    save_json,
    validate_amount,
    validate_currency_code,
)

RATE_SOURCE_CACHE = "cache"
RATE_SOURCE_STUB = "stub"
RATES_STUB_SOURCE_NAME = "StubRatesProvider"
RATES_TTL_SECONDS = 300


def load_users() -> list[User]:
    """
    Загрузить всех пользователей из users.json.
    """
    return [User.from_dict(item) for item in load_json(USERS_FILE, [])]

def save_users(users: list[User]):
    """
    Сохранить список пользователей в users.json.
    """
    save_json(USERS_FILE, [user.to_dict() for user in users])

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
    return [Portfolio.from_dict(item) for item in load_json(PORTFOLIOS_FILE, [])]

def save_portfolios(portfolios: list[Portfolio]):
    """
    Сохранить список портфелей в portfolios.json.
    """
    save_json(PORTFOLIOS_FILE, [portfolio.to_dict() for portfolio in portfolios])

def load_rates_cache() -> dict[str, Any]:
    """
    Загрузить локальный кеш курсов из rates.json.
    """
    return load_json(RATES_FILE, {})

def _read_pair(cache: dict[str, Any], from_code: str, to_code: str) -> dict | None:
    """
    Найти курс пары в кеше: прямой или обратный.
    """
    direct = cache.get(f"{from_code}_{to_code}")
    if isinstance(direct, dict) and "rate" in direct:
        return {"rate": float(direct["rate"]), "updated_at": direct.get("updated_at")}
    reverse = cache.get(f"{to_code}_{from_code}")
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

def _resolve_currency(code: str) -> str:
    """
    Проверить код по реестру валют; неизвестный код выбрасывает CurrencyNotFoundError.
    """
    return get_currency(code).code

def _now_iso() -> str:
    """
    Текущее время в ISO-формате с точностью до секунды.
    """
    return datetime.now().replace(microsecond=0).isoformat()

def _is_fresh(updated_at: str | None, ttl_seconds: int = RATES_TTL_SECONDS) -> bool:
    """
    Проверить, что курс обновлялся не раньше, чем ttl_seconds назад.
    """
    if not updated_at:
        return False
    try:
        moment = datetime.fromisoformat(updated_at)
    except ValueError:
        return False
    now = datetime.now(moment.tzinfo) if moment.tzinfo else datetime.now()
    return (now - moment).total_seconds() <= ttl_seconds

def refresh_rates_cache() -> dict[str, Any]:
    """
    Обновить кеш rates.json свежими курсами.

    Пока Parser Service не подключён, курсы берутся из заглушки
    EXCHANGE_RATES_TO_USD. Сбой источника курсов -> ApiRequestError.
    """
    cache = load_rates_cache()
    now = _now_iso()
    for code, rate in EXCHANGE_RATES_TO_USD.items():
        if code != BASE_CURRENCY:
            cache[f"{code}_{BASE_CURRENCY}"] = {"rate": rate, "updated_at": now}
    cache.pop("source", None)
    cache.pop("last_refresh", None)
    cache["source"] = RATES_STUB_SOURCE_NAME
    cache["last_refresh"] = now
    save_json(RATES_FILE, cache)
    return cache

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

    Берёт курс из кеша rates.json, если он моложе TTL; иначе обновляет кеш
    и считает курс заново. Возвращает словарь: from, to, rate,
    updated_at, source.
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

    cached = None
    try:
        cached = _compute_rate(from_code, to_code, load_rates_cache())
        if cached["source"] == RATE_SOURCE_CACHE and _is_fresh(cached["updated_at"]):
            return cached
    except ValueError:
        pass

    try:
        cache = refresh_rates_cache()
    except ApiRequestError:
        if cached is not None:
            return cached | {"stale": True}
        raise

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
    for key, value in cache.items():
        if isinstance(value, dict) and "_" in key:
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

def register_user(username: str, password: str) -> User:
    """
    Зарегистрировать пользователя и создать для него пустой портфель.
    """
    users = load_users()
    target = username.strip().lower()
    if any(user.username.lower() == target for user in users):
        raise ValueError(f"Имя пользователя '{username.strip()}' уже занято")

    user = User.create(_next_user_id(users), username, password)
    users.append(user)

    portfolios = [
        portfolio
        for portfolio in load_portfolios()
        if portfolio.user_id != user.user_id
    ]
    portfolios.append(Portfolio(user.user_id))

    save_users(users)
    save_portfolios(portfolios)
    return user

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
    for portfolio in load_portfolios():
        if portfolio.user_id == user_id:
            return portfolio
    return Portfolio(user_id)

def get_portfolio_summary(
    user_id: int, base_currency: str = BASE_CURRENCY
) -> dict[str, Any]:
    """
    Сводка по портфелю: балансы кошельков и их стоимость в базовой валюте.
    """
    base = validate_currency_code(base_currency)
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
    portfolios = [
        item for item in load_portfolios() if item.user_id != portfolio.user_id
    ]
    portfolios.append(portfolio)
    portfolios.sort(key=lambda item: item.user_id)
    save_portfolios(portfolios)

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

def buy_currency(
    user_id: int, currency_code: str, amount: float, base_currency: str = BASE_CURRENCY
) -> dict[str, Any]:
    """
    Купить amount единиц валюты: пополнить или создать кошелёк.
    """
    code = _resolve_currency(currency_code)
    amount = validate_amount(amount)
    base = _resolve_currency(base_currency)
    rate = _get_rate_to_base(code, base)

    portfolio = get_portfolio(user_id)
    wallet = portfolio.get_wallet(code) or portfolio.add_currency(code)
    old_balance = wallet.balance
    wallet.deposit(amount)
    save_portfolio(portfolio)

    return {
        "currency_code": code,
        "amount": amount,
        "old_balance": old_balance,
        "new_balance": wallet.balance,
        "rate": rate,
        "base": base,
        "cost": amount * rate,
    }

def sell_currency(
    user_id: int, currency_code: str, amount: float, base_currency: str = BASE_CURRENCY
) -> dict[str, Any]:
    """
    Продать amount единиц валюты.

    Если у пользователя есть кошелёк базовой валюты, выручка зачисляется на него.
    Возвращает словарь: currency_code, amount, old_balance, new_balance,
    rate, base, revenue, base_old_balance/base_new_balance (None без зачисления).
    """
    code = _resolve_currency(currency_code)
    amount = validate_amount(amount)
    base = _resolve_currency(base_currency)

    portfolio = get_portfolio(user_id)
    wallet = portfolio.get_wallet(code)
    if wallet is None:
        raise ValueError(
            f"У вас нет кошелька '{code}'. Добавьте валюту: "
            "она создаётся автоматически при первой покупке."
        )
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
    save_portfolio(portfolio)

    return {
        "currency_code": code,
        "amount": amount,
        "old_balance": old_balance,
        "new_balance": wallet.balance,
        "rate": rate,
        "base": base,
        "revenue": revenue,
        "base_old_balance": base_old_balance,
        "base_new_balance": base_new_balance,
    }
