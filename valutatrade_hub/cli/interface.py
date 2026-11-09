import argparse
import shlex
import sys

from prettytable import PrettyTable

from valutatrade_hub.core import usecases
from valutatrade_hub.core.currencies import CryptoCurrency, get_supported_codes
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
    RateUnavailableError,
    ValutaTradeError,
)
from valutatrade_hub.core.models import User
from valutatrade_hub.core.utils import (
    format_amount,
    format_money,
    parse_iso_datetime,
)
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.logging_config import setup_logging

PROMPT = "> "
EXIT_COMMANDS = {"exit", "quit"}
HELP_COMMANDS = {"help", "?"}
SEPARATOR_WIDTH = 33
RATE_COMMANDS = {"buy", "sell", "get-rate"}

COMMAND_DESCRIPTIONS = {
    "register": "зарегистрировать нового пользователя",
    "login": "войти в систему",
    "show-portfolio": "показать кошельки и итоговую стоимость",
    "buy": "купить валюту",
    "sell": "продать валюту",
    "get-rate": "получить курс одной валюты к другой",
    "currencies": "список поддерживаемых валют",
    "logout": "выйти из учётной записи",
    "update-rates": "обновить курсы из внешних API (Parser Service)",
    "show-rates": "показать курсы из локального кеша",
}


class CliArgumentError(Exception):
    """
    Ошибка разбора аргументов команды.
    """


class CliArgumentParser(argparse.ArgumentParser):
    """
    ArgumentParser, который не завершает программу при ошибке разбора.
    """

    def error(self, message: str):
        raise CliArgumentError(message)


class CliSession:
    """
    Состояние текущей сессии CLI.
    """

    def __init__(self):
        self.current_user: User | None = None


def build_parser() -> CliArgumentParser:
    """
    Собрать парсер всех команд CLI.
    """
    parser = CliArgumentParser(prog="", add_help=False)
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    register = subparsers.add_parser(
        "register", prog="register", help=COMMAND_DESCRIPTIONS["register"]
    )
    register.add_argument("--username", required=True, help="имя пользователя")
    register.add_argument("--password", required=True, help="пароль (≥ 4 символов)")

    login = subparsers.add_parser(
        "login", prog="login", help=COMMAND_DESCRIPTIONS["login"]
    )
    login.add_argument("--username", required=True, help="имя пользователя")
    login.add_argument("--password", required=True, help="пароль")

    show_portfolio = subparsers.add_parser(
        "show-portfolio",
        prog="show-portfolio",
        help=COMMAND_DESCRIPTIONS["show-portfolio"],
    )
    show_portfolio.add_argument(
        "--base",
        default=None,
        help=(
            "базовая валюта (по умолчанию "
            f"{SettingsLoader().get('default_base_currency')})"
        ),
    )

    buy = subparsers.add_parser("buy", prog="buy", help=COMMAND_DESCRIPTIONS["buy"])
    buy.add_argument("--currency", required=True, help="код покупаемой валюты")
    buy.add_argument("--amount", required=True, help="количество (в штуках валюты)")

    sell = subparsers.add_parser(
        "sell", prog="sell", help=COMMAND_DESCRIPTIONS["sell"]
    )
    sell.add_argument("--currency", required=True, help="код продаваемой валюты")
    sell.add_argument("--amount", required=True, help="количество (в штуках валюты)")

    get_rate = subparsers.add_parser(
        "get-rate", prog="get-rate", help=COMMAND_DESCRIPTIONS["get-rate"]
    )
    get_rate.add_argument(
        "--from", dest="from_currency", required=True, help="исходная валюта"
    )
    get_rate.add_argument(
        "--to", dest="to_currency", required=True, help="целевая валюта"
    )

    subparsers.add_parser(
        "currencies", prog="currencies", help=COMMAND_DESCRIPTIONS["currencies"]
    )
    subparsers.add_parser(
        "logout", prog="logout", help=COMMAND_DESCRIPTIONS["logout"]
    )

    update_rates = subparsers.add_parser(
        "update-rates", prog="update-rates", help=COMMAND_DESCRIPTIONS["update-rates"]
    )
    update_rates.add_argument(
        "--source",
        default=None,
        help="только один источник: coingecko или exchangerate (по умолчанию все)",
    )

    show_rates = subparsers.add_parser(
        "show-rates", prog="show-rates", help=COMMAND_DESCRIPTIONS["show-rates"]
    )
    show_rates.add_argument("--currency", default=None, help="курс только этой валюты")
    show_rates.add_argument(
        "--top", default=None, help="N самых дорогих криптовалют"
    )
    show_rates.add_argument(
        "--base", default=None, help="показать все курсы относительно этой валюты"
    )

    return parser

def handle_register(args: argparse.Namespace, session: CliSession):
    """
    Команда register: создать нового пользователя.
    """
    user = usecases.register_user(args.username, args.password)
    print(
        f"Пользователь '{user.username}' зарегистрирован (id={user.user_id}). "
        f"Войдите: login --username {shlex.quote(user.username)} --password ****"
    )

def handle_login(args: argparse.Namespace, session: CliSession):
    """
    Команда login: войти и зафиксировать текущую сессию.
    """
    user = usecases.login_user(args.username, args.password)
    session.current_user = user
    print(f"Вы вошли как '{user.username}'")

def require_login(session: CliSession) -> User:
    """
    Вернуть текущего пользователя или сообщить, что нужно войти.
    """
    if session.current_user is None:
        raise ValueError("Сначала выполните login")
    return session.current_user

def parse_amount(text: str) -> float:
    """
    Преобразовать аргумент --amount в число.
    """
    try:
        return float(text.replace(",", "."))
    except ValueError:
        raise ValueError("'amount' должен быть положительным числом") from None

def handle_show_portfolio(args: argparse.Namespace, session: CliSession):
    """
    Команда show-portfolio.
    """
    user = require_login(session)
    summary = usecases.get_portfolio_summary(user.user_id, args.base)
    base = summary["base"]
    if not summary["wallets"]:
        print(f"Портфель пользователя '{user.username}' пуст: кошельков пока нет")
        return

    print(f"Портфель пользователя '{user.username}' (база: {base}):")
    rows = [
        (
            f"{wallet['currency_code']}: "
            f"{format_money(wallet['currency_code'], wallet['balance'])}",
            format_money(base, wallet["value"]),
        )
        for wallet in summary["wallets"]
    ]
    width = max(len(label) for label, _ in rows)
    for label, value in rows:
        print(f"- {label:<{width}}  -> {value} {base}")
    print("-" * SEPARATOR_WIDTH)
    print(f"ИТОГО: {format_money(base, summary['total'], thousands=True)} {base}")

def handle_buy(args: argparse.Namespace, session: CliSession):
    """
    Команда buy.
    """
    user = require_login(session)
    result = usecases.buy_currency(
        user.user_id, args.currency, parse_amount(args.amount)
    )
    code, base = result["currency_code"], result["base"]
    print(
        f"Покупка выполнена: {format_money(code, result['amount'])} {code} "
        f"по курсу {format_amount(result['rate'])} {base}/{code}"
    )
    print(f"Валюта: {result['currency_info']}")
    print("Изменения в портфеле:")
    print(
        f"- {code}: было {format_money(code, result['old_balance'])} "
        f"- стало {format_money(code, result['new_balance'])}"
    )
    print(
        f"Оценочная стоимость покупки: "
        f"{format_money(base, result['cost'], thousands=True)} {base}"
    )

def print_balance_change(code: str, old_balance: float, new_balance: float):
    """
    Вывести строку изменения баланса кошелька.
    """
    print(
        f"- {code}: было {format_money(code, old_balance)} "
        f"- стало {format_money(code, new_balance)}"
    )

def handle_sell(args: argparse.Namespace, session: CliSession):
    """
    Команда sell.
    """
    user = require_login(session)
    result = usecases.sell_currency(
        user.user_id, args.currency, parse_amount(args.amount)
    )
    code, base = result["currency_code"], result["base"]
    print(
        f"Продажа выполнена: {format_money(code, result['amount'])} {code} "
        f"по курсу {format_amount(result['rate'])} {base}/{code}"
    )
    print(f"Валюта: {result['currency_info']}")
    print("Изменения в портфеле:")
    print_balance_change(code, result["old_balance"], result["new_balance"])
    if result["base_new_balance"] is not None:
        print_balance_change(
            base, result["base_old_balance"], result["base_new_balance"]
        )
    print(
        f"Оценочная выручка: "
        f"{format_money(base, result['revenue'], thousands=True)} {base}"
    )

def format_timestamp(value: str | None) -> str:
    """
    Привести ISO-время к виду 'YYYY-MM-DD HH:MM:SS'.
    """
    moment = parse_iso_datetime(value)
    if moment is None:
        return value or "неизвестно"
    if moment.tzinfo is not None:
        moment = moment.astimezone()
    return moment.strftime("%Y-%m-%d %H:%M:%S")

def handle_get_rate(args: argparse.Namespace, session: CliSession):
    """
    Команда get-rate.
    """
    result = usecases.get_rate(args.from_currency, args.to_currency)
    from_code, to_code, rate = result["from"], result["to"], result["rate"]
    print(
        f"Курс {from_code}->{to_code}: {format_amount(rate)} "
        f"(обновлено: {format_timestamp(result['updated_at'])})"
    )
    if rate:
        print(f"Обратный курс {to_code}->{from_code}: {format_amount(1 / rate)}")

def handle_currencies(args: argparse.Namespace, session: CliSession):
    """
    Команда currencies.
    """
    table = PrettyTable(["Код", "Тип", "Описание"])
    table.align = "l"
    for currency in usecases.list_currencies():
        kind = "CRYPTO" if isinstance(currency, CryptoCurrency) else "FIAT"
        table.add_row([currency.code, kind, currency.get_display_info()])
    print(table)

def handle_logout(args: argparse.Namespace, session: CliSession):
    """
    Команда logout.
    """
    user = require_login(session)
    session.current_user = None
    print(f"Вы вышли из учётной записи '{user.username}'")

def print_progress(level: str, message: str):
    """
    Вывести шаг обновления курсов.
    """
    print(f"{level}: {message}")

def parser_log_hint() -> str:
    """
    Путь к логу Parser Service относительно корня проекта.
    """
    settings = SettingsLoader()
    path = settings.log_path("parser_log_file")
    try:
        return path.relative_to(settings.project_root).as_posix()
    except ValueError:
        return str(path)

def handle_update_rates(args: argparse.Namespace, session: CliSession):
    """
    Команда update-rates.
    """
    try:
        summary = usecases.update_rates(args.source, progress=print_progress)
    except ApiRequestError as error:
        print(error)
        print(f"Update failed. Check {parser_log_hint()} for details.")
        return
    if summary["errors"]:
        print(f"Update completed with errors. Check {parser_log_hint()} for details.")
        return
    print(
        f"Update successful. Total rates updated: {summary['total_updated']}. "
        f"Last refresh: {format_timestamp(summary['last_refresh'])}"
    )

def parse_top(text: str | None) -> int | None:
    """
    Преобразовать аргумент --top в целое число.
    """
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        raise ValueError("'top' должен быть положительным целым числом") from None

def handle_show_rates(args: argparse.Namespace, session: CliSession):
    """
    Команда show-rates.
    """
    result = usecases.get_cached_rates(
        currency=args.currency, top=parse_top(args.top), base=args.base
    )
    print(f"Rates from cache (updated at {format_timestamp(result['last_refresh'])}):")
    for row in result["rows"]:
        print(f"- {row['pair']}: {format_amount(row['rate'])}")

COMMAND_HANDLERS = {
    "register": handle_register,
    "login": handle_login,
    "show-portfolio": handle_show_portfolio,
    "buy": handle_buy,
    "sell": handle_sell,
    "get-rate": handle_get_rate,
    "currencies": handle_currencies,
    "logout": handle_logout,
    "update-rates": handle_update_rates,
    "show-rates": handle_show_rates,
}

def print_help():
    """
    Вывести список доступных команд.
    """
    print("Доступные команды:")
    for command, description in COMMAND_DESCRIPTIONS.items():
        print(f"  {command:<16} {description}")
    print(f"  {'help':<16} показать эту справку")
    print(f"  {'exit':<16} выйти из программы")
    print("Подробнее о команде: <command> --help")

def print_error(command: str, error: Exception):
    """
    Показать сообщение об ошибке с подсказкой по контексту команды.
    """
    print(error)
    if isinstance(error, InsufficientFundsError):
        return
    if isinstance(error, CurrencyNotFoundError):
        print(f"Поддерживаемые валюты: {', '.join(get_supported_codes())}")
        if command == "get-rate":
            print("Справка: get-rate --help")
        else:
            print("Подробнее о валютах: currencies")
    elif isinstance(error, ApiRequestError):
        if command in RATE_COMMANDS:
            ttl = SettingsLoader().get("rates_ttl_seconds")
            print(f"Курсы в кеше старше {ttl} с, а обновить их не удалось.")
        print("Повторите попытку позже или проверьте подключение к сети.")
    elif isinstance(error, RateUnavailableError):
        print("Подробнее о валютах: currencies")

def execute_command(line: str, parser: CliArgumentParser, session: CliSession):
    """
    Разобрать и выполнить одну строку ввода.
    """
    try:
        tokens = shlex.split(line)
    except ValueError as error:
        print(f"Ошибка разбора команды: {error}")
        return
    if not tokens:
        return
    if tokens[0] in HELP_COMMANDS:
        print_help()
        return
    if tokens[0] not in COMMAND_HANDLERS:
        print(f"Неизвестная команда '{tokens[0]}'. Введите help для справки.")
        return

    try:
        args = parser.parse_args(tokens)
    except CliArgumentError as error:
        print(f"Ошибка аргументов: {error}")
        return
    except SystemExit:
        return

    try:
        COMMAND_HANDLERS[args.command](args, session)
    except (ValutaTradeError, ValueError, TypeError) as error:
        print_error(args.command, error)

def main():
    """
    Точка входа CLI: интерактивный цикл чтения команд.
    """
    if hasattr(sys.stdout, "reconfigure"):
        # Символы, которых нет в кодировке консоли, заменяются на "?",
        sys.stdout.reconfigure(errors="replace")
    setup_logging()
    parser = build_parser()
    session = CliSession()
    print("ValutaTrade Hub. Введите help для списка команд, exit для выхода.")
    while True:
        try:
            line = input(PROMPT).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if line in EXIT_COMMANDS:
            break
        execute_command(line, parser, session)
    print("До свидания!")
