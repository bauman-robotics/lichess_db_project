# Stockfish: установка и тест

Скрипты вынесены в отдельную папку `scripts/engine/`.

## Установка

На сервере от root:

```bash
bash scripts/engine/install_stockfish.sh
```

Скрипт ставит пакет `stockfish` из репозитория, проверяет бинарник
и делает короткий UCI-тест (`depth=10`).

## Тест на партиях из базы

Из корня проекта:

```bash
venv/bin/python scripts/engine/test_stockfish.py \
    --player DenNedelin \
    --limit 2 \
    --depth 10 \
    --step 4 \
    --hash 16
```

- `--limit` — сколько партий с `[%eval]` взять (1–5).
- `--depth` — глубина Stockfish.
- `--step` — проверять каждый N-й полуход (1 — все).
- `--max-positions` — общий лимит позиций.
- `--hash` / `--threads` — параметры UCI.

Скрипт сравнивает оценку Stockfish с Lichess `[%eval]` и печатает
время на позицию. Данные в БД не записываются.

## Ограничения сервера

На текущем сервере 1 vCPU и мало свободной RAM. Для тестов
используйте `Hash=16`, `Threads=1`, небольшие `--limit`/`--step`.
Массовый расчёт всех партий на этом сервере не запускать.
