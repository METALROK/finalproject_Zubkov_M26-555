import argparse
import shlex
from datetime import datetime

from valutatrade_hub.core import usecases
from valutatrade_hub.core.currencies import get_supported_codes
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
    ValutaTradeError,
)
from valutatrade_hub.core.models import User
from valutatrade_hub.core.utils import format_amount, format_money
from valutatrade_hub.infra.settings import SettingsLoader

PROMPT = "> "
EXIT_COMMANDS = {"exit", "quit"}
HELP_COMMANDS = {"help", "?"}
SEPARATOR_WIDTH = 33

COMMAND_DESCRIPTIONS = {
    "register": "зарегистрировать нового пользователя",
    "login": "войти в систему",
    "show-portfolio": "показать кошельки и итоговую стоимость",
    "buy": "купить валюту",
    "sell": "продать валюту",
    "get-rate": "получить курс одной валюты к другой",
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
    if not value:
        return "неизвестно"
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return value

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
    if result.get("stale"):
        print(
            "Внимание: курс устарел, обновить его не удалось. "
            "Повторите попытку позже."
        )

COMMAND_HANDLERS = {
    "register": handle_register,
    "login": handle_login,
    "show-portfolio": handle_show_portfolio,
    "buy": handle_buy,
    "sell": handle_sell,
    "get-rate": handle_get_rate,
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
    except InsufficientFundsError as error:
        print(error)
    except CurrencyNotFoundError as error:
        print(error)
        print(f"Поддерживаемые валюты: {', '.join(get_supported_codes())}")
        print("Справка по курсам: get-rate --help")
    except ApiRequestError as error:
        print(error)
        print("Повторите попытку позже или проверьте подключение к сети.")
    except (ValutaTradeError, ValueError, TypeError) as error:
        print(error)

def main():
    """
    Точка входа CLI: интерактивный цикл чтения команд.
    """
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
