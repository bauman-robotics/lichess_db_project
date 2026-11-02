# ♟️ Lichess Database Manager

Веб-приложение для хранения, анализа и визуализации шахматных партий с Lichess в PostgreSQL.

**Что делает:** скачивает ваши партии с Lichess (или любого игрока), сохраняет их в базу данных, строит статистику и помогает разбирать игру — по дебютам, результатам, контролю времени, рейтингу соперников.

**Кому полезно:** шахматистам, которые хотят видеть свою игру в цифрах, анализировать ошибки в дебютах, отслеживать прогресс рейтинга и сравнивать результаты против разных категорий соперников.

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-12+-blue.svg)](https://postgresql.org)
[![Flask](https://img.shields.io/badge/Flask-2.3+-green.svg)](https://flask.palletsprojects.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🎯 Основные возможности

### Загрузка и хранение партий
- Импорт из PGN-файлов
- Скачивание партий через Lichess API (свой аккаунт или любой другой игрок)
- Хранение в PostgreSQL с отдельной таблицей на каждого игрока
- Поддержка локальной и удалённой БД через SSH-туннель

### Анализ и статистика
- **Базовая статистика:** игры, победы, поражения, ничьи, процент побед
- **Рейтинговая статистика:** средний/минимальный/максимальный рейтинг, динамика по контролю времени
- **Анализ дебютов:** топ дебютов по частоте и проценту побед, выявление проблемных дебютов
- **Статистика по длине партий:** распределение по диапазонам ходов, процент побед в каждом
- **Результаты против соперников:** разбивка по категориям «сильнее / слабее / равный»
- **Прогресс рейтинга:** график динамики с отметками результатов и дебютов
- **Фильтр по дебютам:** страница с выборкой партий по названию дебюта, результату и цвету фигур
- **Оценка Stockfish:** график преимущества по ходам и точки ходов игрока/соперника
- **Текущая оценка и Δ хода:** на графике видны оценка позиции, последний ход и изменение оценки
- **Анализ DeepSeek:** разбор партии в нескольких стилях, повторный анализ и авто-подготовка оценок Stockfish
- **Статус анализа:** этапы Stockfish → DeepSeek с прогрессом в кнопке и модалке
- **Избранное и заметки:** единые аннотации к партиям, поиск по заметкам
- **Пагинация:** последние игры, короткие/длинные партии и фильтр партий

### Веб-интерфейс
- Поиск и анализ любого игрока Lichess
- Адаптивный дизайн в стиле Lichess
- Тёмная тема
- Карточки партий на мобильных, таблица на десктопе
- Графики рейтинга и преимущества на Chart.js
- Индикаторы наличия оценок Lichess/Stockfish и анализа DeepSeek
- Мобильная навигация разделов в два ряда (3 × 2)
- Демо-запись интерфейса через Playwright с искусственным курсором

### Видео

- [Обзор сервиса на Vimeo](https://vimeo.com/1242445134)
- [Мобильная версия на Vimeo](https://vimeo.com/1242445133)

### Демо-запись

```bash
demo/.venv/bin/python demo/record_demo.py --scenario demo/scenarios/overview_v5.yaml
demo/.venv/bin/python demo/record_demo.py --scenario demo/scenarios/mobile.yaml
```

Подробнее — в [demo/README.md](demo/README.md).

### Командная строка
- Скрипты для управления БД, импорта, анализа
- Поддержка работы с любым игроком, не только со своим
- Детальный анализ дебютов, партий, игроков

---

## 📋 Оглавление

- [Быстрый старт](#-быстрый-старт)
- [Структура проекта](#-структура-проекта)
- [Требования](#-требования)
- [Установка](#-установка)
- [Настройка](#-настройка)
- [Использование](#-использование)
  - [Работа с базой данных](#-работа-с-базой-данных)
  - [Импорт игр](#-импорт-игр)
  - [Веб-интерфейс](#-веб-интерфейс)
  - [Анализ игр](#-анализ-игр)
  - [Таблицы и поля](#tables)
- [Развёртывание](#deployment)
- [Расширение функциональности](#-расширение-функциональности)
- [Лицензия](#-лицензия)

---

## 🚀 Быстрый старт

Если у вас уже есть Python 3.8+, PostgreSQL и pip:

```bash
# 1. Клонировать репозиторий
git clone <repo-url>
cd lichess_db_project

# 2. Инициализировать проект (создаст venv и поставит зависимости)
python3 scripts/init_project.py

# 3. Активировать окружение
source activate.sh

# 4. Настроить секреты
cp config/secrets.yaml.example config/secrets.yaml
# отредактировать config/secrets.yaml — указать пароль PostgreSQL

# 5. Создать таблицы партий и служебные таблицы
#    (заметки, избранное, очередь импорта, движок, задачи анализа)
python3 scripts/setup_db.py --action create --verbose

# 6. Запустить веб-приложение
python3 run_web.py
```

Откройте в браузере: **http://localhost:5555**

---

## 📁 Структура проекта

```
lichess_db_project/
├── config/                         # Конфигурационные файлы
│   ├── app_config.yaml             # Общие настройки
│   ├── openings.yaml               # Список популярных дебютов
│   ├── secrets.yaml                # 🔒 Секреты (пароли, ключи) — не в git!
│   ├── secrets.yaml.example        # Шаблон для secrets.yaml
│   └── schemas/                    # Схемы таблиц
│       └── v1_lichess_games.yaml
│
├── core/                           # Ядро системы
│   ├── database/                   # Работа с БД
│   │   ├── connection.py           # Подключение (локальное/SSH)
│   │   ├── db_manager.py           # Управление таблицами
│   │   └── schema_loader.py        # Загрузчик схемы
│   ├── models/                     # Модели данных
│   │   └── game.py                 # Модель шахматной партии
│   └── exceptions/                 # Исключения
│
├── services/                       # Сервисы
│   ├── pgn_parser.py               # Парсер PGN файлов
│   ├── lichess_client.py           # Клиент Lichess API
│   └── import_manager.py           # Менеджер импорта
│
├── web_app/                        # Веб-приложение
│   ├── static/                     # CSS, JS
│   │   └── css/
│   │       └── style.css
│   ├── templates/                  # HTML шаблоны
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── player_stats.html
│   │   ├── player_search.html
│   │   └── player_openings.html
│   ├── app.py                      # Flask приложение
│   ├── config.py                   # Веб-конфигурация
│   └── routes.py                   # Маршруты
│
├── scripts/                        # Исполняемые скрипты
│   ├── init_project.py             # Инициализация проекта
│   ├── setup_db.py                 # Управление БД
│   ├── import_games.py             # Импорт игр
│   ├── 01_analyze_games.py         # Анализ игр
│   ├── 02_deep_analysis.py         # Глубокий анализ
│   ├── 03_analyze_opening.py       # Анализ дебютов
│   ├── 04_download_player_games.py # Скачивание игр игрока
│   ├── 05_analyze_player.py        # Анализ игрока
│   └── 06_list_tables.py           # Список таблиц
│
├── data/                           # PGN файлы и данные
│   ├── downloads/                  # Скачанные PGN
│   └── uploads/                    # Загруженные PGN
│
├── tests/                          # Тесты
├── logs/                           # Логи
├── run_web.py                      # Запуск веб-приложения (dev)
├── wsgi.py                         # WSGI entry point (production)
├── requirements.txt                # Зависимости
├── Makefile                        # Упрощение команд
└── README.md                       # Этот файл
```

---

## 📋 Требования

- **Python** 3.8+
- **PostgreSQL** 12+
- **pip** (менеджер пакетов Python)
- **Lichess API токен** — опционально, для приватных игр

---

## 🚀 Установка

### 1. Клонирование репозитория

```bash
git clone <repo-url>
cd lichess_db_project
```

### 2. Инициализация проекта

```bash
# Создаёт виртуальное окружение и устанавливает зависимости
python3 scripts/init_project.py

# Или с пересозданием venv
python3 scripts/init_project.py --force-venv
```

### 3. Активация виртуального окружения

```bash
source activate.sh
```

Или вручную:

```bash
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate      # Windows
```

### 4. Установка зависимостей (если не установлены)

```bash
pip install -r requirements.txt
```

---

## ⚙️ Настройка

### 1. Настройка секретов

```bash
cp config/secrets.yaml.example config/secrets.yaml
```

Отредактируйте `config/secrets.yaml`:

```yaml
# Локальная база данных
local:
  host: "localhost"
  port: 5432
  user: "postgres"
  password: "your_password_here"
  db_name: "lichess_games"

# Lichess API токен (опционально)
lichess:
  api_token: "lip_your_api_token_here"
  username: "your_lichess_username"
```

### 2. Настройка PostgreSQL

Убедитесь, что PostgreSQL запущен:

```bash
sudo systemctl status postgresql   # Linux
brew services list                 # Mac
```

Создайте базу данных (если нужно):

```bash
sudo -u postgres psql
```

```sql
CREATE DATABASE lichess_games;
CREATE USER your_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE lichess_games TO your_user;
\q
```

### 3. Список популярных дебютов

Файл `config/openings.yaml` содержит список дебютов, которые отображаются на странице фильтрации как кликабельные бейджи. Названия должны совпадать с тем, как их пишет Lichess в PGN (`opening_name`).

Если хотите добавить свои — просто допишите в список:

```yaml
openings:
  - "Caro-Kann Defense"
  - "Queen's Gambit Declined"
  - "Sicilian Defense"
  # ...
```

### 4. Анализ Stockfish и DeepSeek

Настройки движка и анализа находятся в `config/app_config.yaml`:

```yaml
engine:
  enabled: true
  path: "/usr/games/stockfish"
  depth: 14

deepseek:
  prompt_key: "game_analysis_shahmaty_eto_kruto"
  engine_prepass: true
```

`engine_prepass: true` означает: перед анализом DeepSeek проверить наличие
оценок и при их отсутствии сначала посчитать Stockfish. Если `engine.enabled:
false` или `engine_prepass: false`, анализ DeepSeek работает без авто-подготовки.

Служебные таблицы `game_annotations`, `import_tasks`, `game_engine_evals`,
`engine_tasks` и `analysis_tasks` создаются командой `setup_db.py --action create`.

---

## 📖 Использование

### 🗄️ Работа с базой данных

```bash
# Создание таблицы
python3 scripts/setup_db.py --action create --verbose

# Просмотр статуса
python3 scripts/setup_db.py --action status --verbose

# Удаление таблицы
python3 scripts/setup_db.py --action drop --drop-table --verbose

# Пересоздание таблицы
python3 scripts/setup_db.py --action recreate --verbose
```

### 📥 Импорт игр

#### Из PGN файла

```bash
# Импорт из файла
python3 scripts/import_games.py --source file --path data/uploads/games.pgn --player "YourName" --verbose

# Использование конфига
python3 scripts/import_games.py
```

#### Через Lichess API

```bash
# Импорт последних 100 игр
python3 scripts/import_games.py --source api --username Hikaru --limit 100 --verbose

# Импорт за определённый период
python3 scripts/import_games.py --source api --username Hikaru --since 2024-01-01 --until 2024-12-31

# Только блиц-игры
python3 scripts/import_games.py --source api --username Hikaru --perf-type blitz --limit 50
```

### 🌐 Веб-интерфейс

```bash
# Запуск веб-приложения
python3 run_web.py
```

Откройте браузер: **http://localhost:5555**

**Возможности веб-интерфейса:**

- 🔍 **Поиск игрока** — введите имя игрока Lichess, партии скачаются автоматически
- 📊 **Статистика** — игры, победы, рейтинг, дебюты, контроль времени
- 📈 **Графики** — динамика рейтинга на Chart.js
- 📖 **Анализ по дебютам** — фильтр партий по названию дебюта, результату и цвету фигур
- 📱 **Адаптивный дизайн** — таблица на десктопе, карточки на мобильном

### 📊 Анализ игр

```bash
# Базовый анализ
python3 scripts/01_analyze_games.py

# Детальный анализ с распределением точности
python3 scripts/01_analyze_games.py --detailed

# Анализ игрока
python3 scripts/01_analyze_games.py --player "Hikaru"

# Глубокий анализ
python3 scripts/02_deep_analysis.py
python3 scripts/02_deep_analysis.py --player "Hikaru"

# Анализ дебютов
python3 scripts/03_analyze_opening.py --list
python3 scripts/03_analyze_opening.py --player "Hikaru" --list
python3 scripts/03_analyze_opening.py --analyze "Caro-Kann Defense"

# Скачивание игр игрока
python3 scripts/04_download_player_games.py --username "Hikaru"
python3 scripts/04_download_player_games.py --username "Hikaru" --limit 100

# Анализ игрока (отдельный скрипт)
python3 scripts/05_analyze_player.py --username "Hikaru"

# Список таблиц в БД
python3 scripts/06_list_tables.py
```

---

<a id="tables" name="tables"></a>

## 🗄️ Таблицы и поля

### `games_<username>`

Отдельная таблица партий на каждого игрока. Имя — `games_` + безопасное
нижнерегистровое имя игрока (`games_dennedelin`). Старая общая таблица
`games` используется только как legacy-совместимость.

| Поле | Тип | Назначение |
|---|---|---|
| `id` | SERIAL PK | Внутренний идентификатор записи |
| `game_id` | VARCHAR(20), UNIQUE | ID партии на Lichess |
| `game_date` | TIMESTAMP | Дата и время партии |
| `time_control` | VARCHAR(20) | Контроль времени |
| `player_color` | VARCHAR(10) | Цвет игрока: `white` / `black` |
| `result` | VARCHAR(10) | `Win` / `Loss` / `Draw` |
| `accuracy` | DECIMAL(5,2) | Точность, если есть |
| `move_count` | INTEGER | Количество полуходов |
| `opening_name` | VARCHAR(200) | Дебют |
| `opponent_name` | VARCHAR(100) | Соперник |
| `my_rating` | INTEGER | Рейтинг игрока |
| `opponent_rating` | INTEGER | Рейтинг соперника |
| `opponent_games_count` | INTEGER | Число игр соперника |
| `game_analysis` | TEXT | Текст анализа DeepSeek |
| `game_url` | VARCHAR(200) | Ссылка на Lichess |
| `pgn_moves` | TEXT | PGN с ходами и `[%eval]`, если есть |
| `import_source` | VARCHAR(20) | `file` / `api` |
| `created_at` | TIMESTAMP | Создано |
| `updated_at` | TIMESTAMP | Обновлено |

### `game_annotations`

Единая таблица заметок и избранного. Первичный ключ —
`(player_username, game_id)`.

| Поле | Тип | Назначение |
|---|---|---|
| `player_username` | VARCHAR(100) PK | Игрок |
| `game_id` | VARCHAR(20) PK | Партия |
| `game_date` | TIMESTAMP | Дата партии (снимок) |
| `opponent_name` | VARCHAR(100) | Соперник (снимок) |
| `opponent_rating` | INTEGER | Рейтинг соперника |
| `player_color` | VARCHAR(10) | Цвет игрока |
| `result` | VARCHAR(10) | Результат |
| `opening_name` | VARCHAR(200) | Дебют |
| `time_control` | VARCHAR(20) | Контроль |
| `move_count` | INTEGER | Полуходы |
| `my_rating` | INTEGER | Рейтинг игрока |
| `game_url` | VARCHAR(200) | Ссылка |
| `note` | TEXT | Текст заметки |
| `is_favorite` | BOOLEAN | Избранное |
| `created_at` | TIMESTAMPTZ | Создано |
| `updated_at` | TIMESTAMPTZ | Обновлено |

### `import_tasks`

Очередь фонового импорта и догрузки игр.

| Поле | Тип | Назначение |
|---|---|---|
| `task_id` | VARCHAR(36) PK | ID задачи |
| `username` | VARCHAR(100) | Игрок |
| `mode` | VARCHAR(20) | `fill` / `refresh` |
| `target_limit` | INTEGER | Целевое число игр |
| `status` | VARCHAR(20) | `queued` / `running` / `done` / `error` |
| `created_at` | TIMESTAMPTZ | Создано |
| `started_at` | TIMESTAMPTZ | Начато |
| `finished_at` | TIMESTAMPTZ | Завершено |
| `saved` | INTEGER | Сохранено игр |
| `total` | INTEGER | Всего обработано |
| `error` | TEXT | Ошибка |

### `game_engine_evals`

Оценки Stockfish по позициям. Ключ — `(player_username, game_id, ply)`.

| Поле | Тип | Назначение |
|---|---|---|
| `player_username` | VARCHAR(100) PK | Игрок |
| `game_id` | VARCHAR(20) PK | Партия |
| `ply` | INTEGER PK | Номер полухода |
| `san` | VARCHAR(20) | Ход в SAN |
| `eval_cp` | INTEGER | Оценка в сантипешках |
| `mate` | INTEGER | Мат в N ходов |
| `depth` | INTEGER | Глубина расчёта |
| `engine` | VARCHAR(50) | Название движка |
| `created_at` | TIMESTAMPTZ | Создано |

### `engine_tasks`

Очередь фонового анализа Stockfish.

| Поле | Тип | Назначение |
|---|---|---|
| `task_id` | VARCHAR(36) PK | ID задачи |
| `player_username` | VARCHAR(100) | Игрок |
| `game_id` | VARCHAR(20) | Партия |
| `depth` | INTEGER | Глубина |
| `status` | VARCHAR(20) | `queued` / `running` / `done` / `error` |
| `progress` | INTEGER | Обработано полуходов |
| `total` | INTEGER | Всего полуходов |
| `error` | TEXT | Ошибка |
| `created_at` | TIMESTAMPTZ | Создано |
| `started_at` | TIMESTAMPTZ | Начато |
| `finished_at` | TIMESTAMPTZ | Завершено |

### `analysis_tasks`

Очередь анализа DeepSeek и стадии подготовки.

| Поле | Тип | Назначение |
|---|---|---|
| `task_id` | TEXT PK | ID задачи |
| `username` | TEXT | Игрок |
| `game_id` | TEXT | Партия |
| `status` | TEXT | `running` / `done` / `error` |
| `started_at` | TIMESTAMP | Начато |
| `finished_at` | TIMESTAMP | Завершено |
| `error` | TEXT | Ошибка |
| `stage` | VARCHAR(20) | `engine` / `deepseek` |
| `progress` | INTEGER | Прогресс Stockfish |
| `total` | INTEGER | Всего позиций Stockfish |

Все служебные таблицы создаются идемпотентно командой:

```bash
python3 scripts/setup_db.py --action create
```

<a id="deployment" name="deployment"></a>

## 🖥️ Развёртывание

Для продакшена рекомендуется запускать через **gunicorn** за **nginx** с HTTPS.

Обновление на сервере по SSH: `python scripts/deploy/update_remote.py`
(настройка и безопасность — в [docs/deployment.md](docs/deployment.md)).

### Пример systemd-сервиса

Создайте `/etc/systemd/system/lichess-analyzer.service`:

```ini
[Unit]
Description=Lichess Analyzer Web Application (Gunicorn)
After=network.target postgresql.service

[Service]
Type=simple
User=arkhan
Group=arkhan
WorkingDirectory=/home/arkhan/Andrey/lichess_db_project
Environment="PATH=/home/arkhan/Andrey/lichess_db_project/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONPATH=/home/arkhan/Andrey/lichess_db_project"
Environment="PRODUCTION=True"
ExecStart=/home/arkhan/Andrey/lichess_db_project/venv/bin/gunicorn \
    --workers 3 \
    --bind 0.0.0.0:5555 \
    --timeout 300 \
    --graceful-timeout 300 \
    wsgi:app
Restart=always
RestartSec=10
StandardOutput=append:/home/arkhan/Andrey/lichess_db_project/logs/app.log
StandardError=append:/home/arkhan/Andrey/lichess_db_project/logs/error.log

[Install]
WantedBy=multi-user.target
```

Активировать:

```bash
sudo systemctl daemon-reload
sudo systemctl enable lichess-analyzer
sudo systemctl start lichess-analyzer
```

### Пример nginx-конфига

```nginx
location /lichess-analyzer/ {
    rewrite ^/lichess-analyzer/(.*) /$1 break;
    proxy_pass http://127.0.0.1:5555;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Увеличено для долгих запросов (скачивание игр с Lichess)
    proxy_connect_timeout 300s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;
    send_timeout 300s;
}

location /lichess-analyzer/static/ {
    alias /home/arkhan/Andrey/lichess_db_project/web_app/static/;
    expires 30d;
    add_header Cache-Control "public, immutable";
}
```

**Важно:** если статика лежит в домашней директории пользователя, а nginx работает под `www-data`, нужно дать nginx право входа в директорию:

```bash
sudo setfacl -m u:www-data:x /home/arkhan
```

Без этого nginx вернёт **403 Forbidden** на `style.css` и другие файлы статики.

---

## 🔧 Расширение функциональности

Проект спроектирован модульно. Что можно добавить:

- **Классификация ошибок Stockfish** — blunder / mistake / inaccuracy по каждой позиции
- **Сортировка** таблиц по клику на заголовок
- **Экспорт** выборки в CSV/JSON
- **Сравнение двух игроков** — бок о бок
- **Расширенные фильтры** — произвольные комбинации с сохранением в URL

---

## 📄 Лицензия

MIT License. См. файл [LICENSE](LICENSE).