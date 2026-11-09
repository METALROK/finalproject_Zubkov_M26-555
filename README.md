# finalproject_Zubkov_M26-555 — ValutaTrade Hub

Консольное приложение, имитирующее работу валютного кошелька: регистрация
пользователей, портфель фиатных и криптовалют, покупка/продажа и курсы валют.

## Структура

```
data/                    # users.json, portfolios.json, rates.json
valutatrade_hub/
  core/                  # models.py, usecases.py, utils.py, currencies.py, exceptions.py
  infra/                 # settings.py (SettingsLoader), database.py (DatabaseManager)
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
