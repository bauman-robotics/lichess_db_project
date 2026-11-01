# Анализ движком и график преимущества

## Конфиг

```yaml
engine:
  enabled: true          # false — старый layout без графика и движка
  path: "/usr/games/stockfish"
  depth: 14
  hash_mb: 16
  threads: 1
  nice: 19
```

`engine.enabled: false` отключает кнопку, график и фоновый worker,
оставляя текущую страницу просмотра без изменений.

## Как работает

- Если в PGN есть Lichess `[%eval]`, график строится сразу.
- Если оценок нет, показывается кнопка «🧠 Анализ движком».
- Задача выполняется в фоне, прогресс виден на странице.
- Оценки сохраняются в `game_engine_evals` и переиспользуются.
- График — под доской; кнопка «📈 График» сворачивает/разворачивает.
- Клик по точке переводит доску на этот полуход.

## Таблицы

- `game_engine_evals` — `eval_cp`/`mate` по полуходам.
- `engine_tasks` — очередь задач: одна running-задача глобально.

## Миграция

```bash
python scripts/migrations/004_engine_analysis.py --status
python scripts/migrations/004_engine_analysis.py --apply
```
