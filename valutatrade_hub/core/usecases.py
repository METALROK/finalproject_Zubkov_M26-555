from datetime import datetime
from typing import Any

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
    validate_currency_code,
)

RATE_SOURCE_CACHE = "cache"
RATE_SOURCE_STUB = "stub"


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

def get_rate(from_currency: str, to_currency: str) -> dict[str, Any]:
    """
    Единый контракт получения курса FROM -> TO.
    """
    from_code = validate_currency_code(from_currency)
    to_code = validate_currency_code(to_currency)
    result: dict[str, Any] = {"from": from_code, "to": to_code}

    if from_code == to_code:
        updated_at = datetime.now().replace(microsecond=0).isoformat()
        return result | {"rate": 1.0, "updated_at": updated_at, "source": "fixed"}

    cache = load_rates_cache()
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
