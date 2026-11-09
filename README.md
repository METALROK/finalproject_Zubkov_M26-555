# finalproject_Zubkov_M26-555 — ValutaTrade Hub

Консольное приложение, имитирующее работу валютного кошелька: регистрация
пользователей, портфель фиатных и криптовалют, покупка/продажа и курсы валют.

## Структура

```
data/                    # users.json, portfolios.json, rates.json, exchange_rates.json
valutatrade_hub/
  core/                  # models.py, usecases.py, utils.py, currencies.py, exceptions.py
  infra/                 # settings.py (SettingsLoader), database.py (DatabaseManager)
  parser_service/        # config.py (ParserConfig), API-клиенты, обновление курсов
  logging_config.py      # настройка логов (формат, уровень, ротация)
  decorators.py          # @log_action
  cli/                   # interface.py
main.py
pyproject.toml
```

## Установка и запуск

```bash
make install    # uv sync
make project    # uv run project
make lint       # uv run ruff check .
```

## Команды CLI и ошибки

| Команда | Пример | Возможные ошибки |
|---|---|---|
| `register` | `register --username alice --password 1234` | `Имя пользователя 'alice' уже занято`; `Пароль должен быть не короче 4 символов` |
| `login` | `login --username alice --password 1234` | `Пользователь 'alice' не найден`; `Неверный пароль` |
| `show-portfolio` | `show-portfolio --base EUR` | `Сначала выполните login`; `Неизвестная базовая валюта 'ABC'` |
| `buy` | `buy --currency BTC --amount 0.05` | `Сначала выполните login`; `'amount' должен быть положительным числом`; `Неизвестная валюта 'XYZ'`; `Не удалось получить курс для BTC->USD` |
| `sell` | `sell --currency BTC --amount 0.01` | `Сначала выполните login`; `У вас нет кошелька 'BTC'. ...`; `Недостаточно средств: доступно 0.0400 BTC, требуется 0.0500 BTC`; `Неизвестная валюта 'XYZ'` |
| `get-rate` | `get-rate --from USD --to BTC` | `Неизвестная валюта 'XYZ'`; `Курс USD->BTC недоступен. Повторите попытку позже.`; `Ошибка при обращении к внешнему API: ...` |

### Доменные исключения (`valutatrade_hub/core/exceptions.py`)

| Исключение | Где возникает | Что показывает CLI |
|---|---|---|
| `InsufficientFundsError` | `Wallet.withdraw()` -> `sell` | текст ошибки как есть |
| `CurrencyNotFoundError` | `currencies.get_currency()` -> `buy`, `sell`, `get-rate` | текст ошибки + список поддерживаемых валют и подсказка `get-rate --help` |
| `ApiRequestError` | обновление кеша курсов (заглушка / Parser Service) | текст ошибки + предложение повторить позже / проверить сеть |
| `WalletNotFoundError` | `sell` - у пользователя нет кошелька в этой валюте | текст ошибки |
| `RateUnavailableError` | `get_rate()`, `buy`, `sell` - курса нет ни в кеше, ни у источника | текст ошибки |

Все доменные исключения наследуются от `ValutaTradeError`.

## Конфигурация (`SettingsLoader`)

Настройки читаются один раз синглтоном `valutatrade_hub.infra.settings.SettingsLoader`
из секции `[tool.valutatrade]` в `pyproject.toml`. Любой ключ можно переопределить
переменной окружения `VALUTATRADE_<КЛЮЧ>` (например, `VALUTATRADE_RATES_TTL_SECONDS=60`).

| Ключ | По умолчанию | Назначение |
|---|---|---|
| `data_dir` | `data` | каталог с JSON-файлами |
| `users_file` / `portfolios_file` / `rates_file` | `users.json` / `portfolios.json` / `rates.json` | файлы данных |
| `exchange_rates_file` | `exchange_rates.json` | история курсов (Parser Service) |
| `rates_ttl_seconds` | `300` | время «свежести» курса в кеше |
| `default_base_currency` | `USD` | базовая валюта по умолчанию |
| `log_dir` / `log_file` | `logs` / `actions.log` | путь к логам |
| `log_format` | `string` | формат логов: `string` или `json` |
| `log_level` | `INFO` | уровень логирования |
| `log_max_bytes` / `log_backup_count` | `1048576` / `3` | ротация логов |

Методы: `get(key, default)`, `reload()`, `data_path(file_key)`, `log_path()`, `as_dict()`.

Доступ к JSON-файлам идёт через синглтон `valutatrade_hub.infra.database.DatabaseManager`
(`load_users/save_users`, `load_portfolios/save_portfolios`, `load_rates/save_rates`),
запись атомарная (временный файл -> переименование).

## Логирование (`@log_action`)

Доменные операции `register_user`, `login_user`, `buy_currency`, `sell_currency`
в `core/usecases.py` обёрнуты декоратором `@log_action` (`valutatrade_hub/decorators.py`);
для `buy`/`sell` включён `verbose=True` (состояние кошелька до/после).
Декоратор пишет запись на уровне INFO и не глотает исключения - фиксирует их и пробрасывает дальше.
Пароль в лог не попадает.

Поля: `timestamp`, `action` (REGISTER/LOGIN/BUY/SELL), `user`, `user_id`, `currency`, `amount`,
`rate`, `base`, `before`/`after` (verbose), `result` (OK/ERROR), `error_type`, `error_message`.

Пример (`logs/actions.log`, формат `string`):

```
INFO 2026-11-09T22:25:12 BUY user='alice' user_id=1 currency='BTC' amount=0.0500 rate=59337.21 base='USD' before=0.0000 after=0.0500 result=OK
INFO 2026-11-09T22:25:12 SELL user='alice' user_id=1 currency='BTC' amount=1.0000 result=ERROR error_type='InsufficientFundsError' error_message='Недостаточно средств: доступно 0.0400 BTC, требуется 1.0000 BTC'
```

Настройка - `valutatrade_hub/logging_config.py` (`setup_logging()`, вызывается при старте CLI):
формат `string` (по умолчанию) или `json` (`log_format`), уровень INFO (для отладки `log_level = "DEBUG"`),
ротация по размеру файла: `log_max_bytes` = 1 МБ, `log_backup_count` = 3 (`actions.log.1` ... `actions.log.3`).

## Parser Service: ключ API и конфигурация

Курсы получаются из двух источников: **CoinGecko** (криптовалюты, ключ не нужен)
и **ExchangeRate-API** (фиат, нужен бесплатный ключ с https://www.exchangerate-api.com/).

Ключ **не хранится в коде**. Задайте его одним из способов:

- переменная окружения: `export EXCHANGERATE_API_KEY=ваш_ключ` (Git Bash) /
  `set EXCHANGERATE_API_KEY=ваш_ключ` (cmd);
- файл `.env` в корне проекта (он в `.gitignore`): скопируйте `.env.example` в `.env`
  и впишите ключ.

Все параметры сервиса - в `valutatrade_hub/parser_service/config.py` (`ParserConfig`):
эндпоинты, `BASE_CURRENCY = "USD"`, `FIAT_CURRENCIES = ("EUR", "GBP", "RUB")`,
`CRYPTO_CURRENCIES = ("BTC", "ETH", "SOL")`, `CRYPTO_ID_MAP` (тикер -> ID CoinGecko),
`REQUEST_TIMEOUT = 10` с, пути к `data/rates.json` и `data/exchange_rates.json`.
