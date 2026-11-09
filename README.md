# finalproject_Zubkov_M26-555 — ValutaTrade Hub

Консольное приложение, имитирующее работу валютного кошелька: регистрация
пользователей, портфель фиатных и криптовалют, покупка/продажа и курсы валют.

## Структура

```
data/                    # users.json, portfolios.json, rates.json
valutatrade_hub/
  core/                  # models.py, usecases.py, utils.py
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
