import argparse
import shlex

from valutatrade_hub.core import usecases
from valutatrade_hub.core.models import User

PROMPT = "> "
EXIT_COMMANDS = {"exit", "quit"}
HELP_COMMANDS = {"help", "?"}

COMMAND_DESCRIPTIONS = {
    "register": "зарегистрировать нового пользователя",
    "login": "войти в систему",
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

COMMAND_HANDLERS = {
    "register": handle_register,
    "login": handle_login,
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
