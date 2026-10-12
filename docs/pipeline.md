# Пайплайн: от YouTube-видео до промпта анализа партий


Как появился третий промпт `game_analysis_shahmaty_eto_kruto` —
саркастический разбор партий в стиле канала **«Шахматы — это Круто»**.

## Общая схема

```
YouTube (канал «Шахматы — это Круто»)
    ↓ [youtube-playlist-downloader]
30 × mp3 + *_punctuated.txt
    ↓ [lichess_db_project: cleanup_vosk.txt → flash]
30 × *_cleaned.txt
    ↓ [extract_markers.txt → flash]
30 × *_markers.md
    ↓ [build_style_guide.txt → v4-pro]
style_guide.md (справочник стиля, 621 строка)
    ↓ [ручная выжимка + {style_guide_block}]
game_analysis_shahmaty_eto_kruto (промпт)
```

## Два проекта

### 1. youtube-playlist-downloader

**Repo:** https://github.com/bauman-robotics/youtube-playlist-downloader

**Что делает:**
- Скачивает видео/аудио с YouTube (yt-dlp).
- Транскрибирует через Vosk (ASR).
- Расставляет пунктуацию (punctuators).
- Опционально — LLM-обработка (DeepSeek).

**Что мы взяли:** 30 транскрибаций (`*_punctuated.txt`) с канала
«Шахматы — это Круто» — разборы шахматных партий.

**Пайплайн проекта:**
```
YouTube → ytdl.py → transcribe.py (Vosk) → punctuate.py → *_punctuated.txt
```

### 2. lichess_db_project (этот)

**Что делает:** анализатор шахматных партий (PostgreSQL + Flask + DeepSeek).

**Что мы сделали:** извлекли стиль комментатора из 30 транскрибаций
и построили промпт для саркастического разбора партий.
## Шаги (в lichess_db_project)

### Шаг 1. Очистка транскрипций (Vosk)

**Скрипт:** `scripts/03_transcript_style/01_cleanup_vosk.py`
**Промпт:** `config/prompts/cleanup_vosk.txt`
**Модель:** flash

Исправляет только **явные ошибки** ASR:
- Имена: «Корчму» → «Корчной», «Гаспара» → «Каспаров».
- Термины: «диарея» → «диагональ», «аслан» → «фланг».
- Поля: «це пять» → «c5», «бы два» → «b2».
- Технические артефакты: `<unk>`.

**Не трогает** авторские обороты, порядок слов, стиль.

**Вход:** `data/chess_transcripts/*_punctuated.txt` (30 файлов).
**Выход:** `data/chess_transcripts/cleaned/*_cleaned.txt`.

### Шаг 2. Извлечение стилевых маркеров

**Скрипт:** `scripts/03_transcript_style/02_extract_markers.py`
**Промпт:** `config/prompts/extract_markers.txt`
**Модель:** flash

Из каждой транскрибации извлекает:
1. Метафоры и сравнения (5-10, дословно).
2. Юмор и иронию (3-5, дословно).
3. Речевые обороты (5-10, дословно).
4. Эмоциональные приёмы (3-5).

**Не анализирует партию.** **Не пересказывает.**

**Вход:** 30 × `cleaned/*_cleaned.txt`.
**Выход:** 30 × `data/chess_transcripts/markers/*_markers.md` (132 KB).

### Шаг 3. Сводный справочник стиля

**Скрипт:** `scripts/03_transcript_style/03_build_style_guide.py`
**Промпт:** `config/prompts/build_style_guide.txt`
**Модель:** v4-pro

Собирает 30 наборов маркеров в **единый** справочник:
1. Метафоры по фигурам / действиям / позициям.
2. Речевые обороты по функциям.
3. Приёмы юмора.
4. Эмоциональные приёмы.
5. Тон и атмосфера.
6. Готовые фразы-конструкции.

**Фильтрация:**
- Убрать имена шахматистов.
- Убрать Vosk-мусор.
- Оставить шахматные термины-образы.

**Вход:** 30 × `markers/*_markers.md`.
**Выход:** `data/chess_transcripts/style_guide.md` (621 строка, 26 KB).

**Пост-обработка (скриптом):**
- Убраны YouTube-призывы (лайки, подписки, колокольчик).
- Убраны приветствия / прощания.
- Убраны имена (Михаил, Карпов, Таль и т. п.).

### Шаг 4. Промпт game_analysis_shahmaty_eto_kruto

**Файл:** `config/deepseek_prompts.yaml`
**Секция:** `game_analysis_shahmaty_eto_kruto`

**Структура:**
- Роль: комментатор в стиле канала.
- Структура: 4 пункта (дебют / перелом / ошибки / рекомендации)
  + короткий вывод.
- Стиль: ~13 метафор, ~7 оборотов, ~5 эмоций, ~4 приёма юмора.
- Примеры фраз (9 штук).
- Правила: нотация, PGN, без «мата» без `#`, дебюты, материал.

**`{style_guide_block}`** в `user_template`:
- При **каждом** анализе партии в `user`-промпт вставляется
  **полный `style_guide.md`** (26 KB).
- Функция `load_style_guide()` в `services/deepseek_analyzer.py`.
- Если файла **нет** — блок **пустой** (старые промпты работают).

## Интеграция в deepseek_analyzer.py

**Патч (коммит `cb498f0`):**
- `STYLE_GUIDE_FILE` — путь к `style_guide.md`.
- `load_style_guide()` — читает файл.
- `build_prompt(..., style_guide=None)` — новый параметр.
- `analyze_game()` — читает гайд, передаёт в `build_prompt`.

**Обратная совместимость:** старые промпты (`game_analysis`,
`game_analysis_sarcastic`) **без** `{style_guide_block}` — работают
как раньше.

## Стоимость

**Построение (разово):**
- 30 × cleanup (flash): ~0.1 RUB.
- 30 × extract_markers (flash): ~0.1 RUB.
- 2 × build_style_guide (v4-pro): ~1.0 RUB.
- **Итого:** ~1.2 RUB.

**Анализ партии (с гайдом):**
- Prompt: ~7500 токенов (гайд 6000 + PGN 1500).
- Completion: ~500 токенов.
- **Стоимость:** flash ~0.01 RUB, v4-pro ~0.05-0.1 RUB.

## Файлы

### Скрипты
- `scripts/03_transcript_style/01_cleanup_vosk.py`
- `scripts/03_transcript_style/02_extract_markers.py`
- `scripts/03_transcript_style/03_build_style_guide.py`

### Промпты
- `config/prompts/cleanup_vosk.txt`
- `config/prompts/extract_markers.txt`
- `config/prompts/build_style_guide.txt`

### Данные
- `data/chess_transcripts/*_punctuated.txt` (30, gitignored)
- `data/chess_transcripts/cleaned/*_cleaned.txt` (30, gitignored)
- `data/chess_transcripts/markers/*_markers.md` (30, 132 KB)
- `data/chess_transcripts/style_guide.md` (26 KB)

### Промпт
- `config/deepseek_prompts.yaml` → `game_analysis_shahmaty_eto_kruto`

## Ссылки

- **youtube-playlist-downloader:**
  https://github.com/bauman-robotics/youtube-playlist-downloader
- **Канал «Шахматы — это Круто»:** 30 видео с разборами партий.
- **CHANGELOG:** `CHANGELOG.md` → iteration 0.2.
- **Bundle для нового чата:** `docs/bundle/prompt.md`.

## Коммиты

- `cb498f0` — feat(analysis): третий промпт — стиль канала «Шахматы — это Круто».
- `03c6f10` — chore(style_guide): убрать зрительские фразы и имена.
- `26991f0` — feat(prompt): правила про дебюты и материал.
