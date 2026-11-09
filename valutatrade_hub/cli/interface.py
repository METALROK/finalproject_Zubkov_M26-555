import argparse
import shlex

from valutatrade_hub.core import usecases
from valutatrade_hub.core.models import BASE_CURRENCY, CRYPTO_CURRENCIES, User
from valutatrade_hub.core.utils import format_amount

PROMPT = "> "
EXIT_COMMANDS = {"exit", "quit"}
HELP_COMMANDS = {"help", "?"}
FIAT_DECIMALS = 2
CRYPTO_DECIMALS = 4
SEPARATOR_WIDTH = 33

COMMAND_DESCRIPTIONS = {
    "register": "зарегистрировать нового пользователя",
    "login": "войти в систему",
    "show-portfolio": "показать кошельки и итоговую стоимость",
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
        default=BASE_CURRENCY,
        help=f"базовая валюта (по умолчанию {BASE_CURRENCY})",
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

def format_money(currency_code: str, value: float, thousands: bool = False) -> str:
    """
    Отформатировать сумму.
    """
    if currency_code in CRYPTO_CURRENCIES:
        return format_amount(value, min_decimals=CRYPTO_DECIMALS)
    if thousands:
        return f"{value:,.{FIAT_DECIMALS}f}"
    return f"{value:.{FIAT_DECIMALS}f}"

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
        print(f"- {label:<{width}}  → {value} {base}")
    print("-" * SEPARATOR_WIDTH)
    print(f"ИТОГО: {format_money(base, summary['total'], thousands=True)} {base}")

COMMAND_HANDLERS = {
    "register": handle_register,
    "login": handle_login,
    "show-portfolio": handle_show_portfolio,
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
    except (ValueError, TypeError) as error:
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
