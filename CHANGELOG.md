# Changelog

Все значимые изменения проекта. Формат: `дата — итерация — краткое описание`.

---

## [2026-10-13] iteration 0.2 — третий промпт анализа: стиль канала «Шахматы — это Круто»

Добавлен **третий вариант промпта** для анализа партий — саркастический
в стиле канала «Шахматы — это Круто». Построен из 30 транскрибаций
видео канала через пайплайн: очистка → маркеры → сводный гайд → промпт.

### Добавлено

**Промпты:**
- `game_analysis_shahmaty_eto_kruto` в `config/deepseek_prompts.yaml` —
  саркастический разбор в стиле канала (метафоры, обороты, юмор).
  В `user_template` добавлен `{style_guide_block}` — вставляется
  полный справочник стиля.
- `config/prompts/extract_markers.txt` — промпт извлечения стилевых
  маркеров из транскрипции (метафоры, юмор, обороты, эмоции).
- `config/prompts/build_style_guide.txt` — промпт свода 30 маркеров
  в единый справочник.

**Скрипты** (`scripts/03_transcript_style/`):
- `01_cleanup_vosk.py` — очистка транскрипций Vosk через flash
  (переоформлен для воспроизводимости).
- `02_extract_markers.py` — извлечение стилевых маркеров из
  `cleaned/*_cleaned.txt` → `markers/*_markers.md` (flash).
- `03_build_style_guide.py` — свод 30 маркеров в единый
  `data/chess_transcripts/style_guide.md` (v4-pro).

**Данные:**
- `data/chess_transcripts/markers/*_markers.md` — 30 файлов
  стилевых маркеров (по одному на транскрибацию).
- `data/chess_transcripts/style_guide.md` — справочник стиля
  (649 строк, ~4200 слов): метафоры по фигурам/действиям/позициям,
  речевые обороты по функциям, приёмы юмора, эмоциональные приёмы,
  тон и атмосфера, готовые фразы-конструкции.

### Изменено

**`services/deepseek_analyzer.py`:**
- `STYLE_GUIDE_FILE` — путь к `style_guide.md`.
- `load_style_guide()` — читает `style_guide.md`, если есть.
- `build_prompt(game, prompts, player_name, style_guide=None)` —
  новый параметр `style_guide`; формирует `{style_guide_block}`.
  **Обратная совместимость:** старые промпты без placeholder
  работают как раньше.
- `analyze_game()` — читает гайд и передаёт в `build_prompt`.
- **Фикс `move_count`:** в БД хранятся **полуходы**, в промпт
  отдаём **полные ходы** (`(plies + 1) // 2`). 57 полуходов → 29 ходов.
- **Фикс `player_color`:** в БД колонка `player_color`, а не `color`.
  Теперь `game.get('color') or game.get('player_color') or '?'`.

**`config/app_config.yaml`:**
- `prompt_key: game_analysis_shahmaty_eto_kruto` (активный промпт).

### E2E

Партия `dennedelin` vs `lichess AI level 2` (Bird Opening, 29 ходов, `29.Qg5#`).

- **`game_analysis`** — нейтральный разбор (1165 символов):
  «Ключевая идея белых — контроль e5...».
- **`game_analysis_sarcastic`** — сарказм без канала (1562 символа):
  «калькулятор с похмелья», «умудрились устроить драму».
- **`game_analysis_shahmaty_eto_kruto`** — канальный стиль (1600 символов):
  «Итак, друзья», «пешечная лавина», «вцепились зубами», «сложили оружие».

**Стоимость всего пайплайна:** ~1.5 RUB
(30 × extract_markers + 2 × v4-pro свод).

### Открыто (TODO)

- **Фикс парсера PGN:** `move_count` в БД — **полуходы**, что
  сбивает модель. Сейчас лечится в `build_prompt`, но **правильнее**
  хранить **полные ходы** в БД.
- **`build_prompt` и `player_color`:** в `web_app/routes.py` может
  быть **свой** маппинг `player_color` → `color`. Проверить, что
  не дублируется.
- **Обновить `about.html`:** добавить третий промпт в список.
- **README / docs:** описать пайплайн
  `cleanup → markers → style_guide → prompt`.
- **Убрать `.bak`-файлы** после финализации.

### Ссылки

- Справочник: `data/chess_transcripts/style_guide.md`
- Промпт: `config/deepseek_prompts.yaml` → `game_analysis_shahmaty_eto_kruto`
- Скрипты: `scripts/03_transcript_style/`

---

## [2026-10-13] iteration 0.1 — инициализация changelog

Файл создан. Предыдущие изменения (до этой итерации) не логировались.
