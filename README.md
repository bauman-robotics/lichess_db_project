# ♟️ Lichess Database Manager

Система для хранения, анализа и визуализации шахматных партий с Lichess в PostgreSQL с веб-интерфейсом.

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-12+-blue.svg)](https://postgresql.org)
[![Flask](https://img.shields.io/badge/Flask-2.3+-green.svg)](https://flask.palletsprojects.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📋 Оглавление

- [Возможности](#-возможности)
- [Структура проекта](#-структура-проекта)
- [Требования](#-требования)
- [Установка](#-установка)
- [Настройка](#-настройка)
- [Использование](#-использование)
  - [Работа с базой данных](#-работа-с-базой-данных)
  - [Импорт игр](#-импорт-игр)
  - [Веб-интерфейс](#-веб-интерфейс)
  - [Анализ игр](#-анализ-игр)
- [Скриншоты](#-скриншоты)
- [Расширение функциональности](#-расширение-функциональности)
- [Лицензия](#-лицензия)

---

## ✨ Возможности

### 📊 Управление данными
- ✅ Хранение шахматных партий в PostgreSQL
- ✅ Импорт из PGN файлов
- ✅ Загрузка через Lichess API
- ✅ Поддержка локальной и удаленной БД (через SSH)
- ✅ Безопасное хранение секретов

### 🔍 Анализ игр
- ✅ Базовая статистика (игры, победы, поражения, ничьи)
- ✅ Рейтинговая статистика по контролю времени
- ✅ Анализ дебютов с процентом побед
- ✅ Статистика по длине партий
- ✅ Прогресс рейтинга с графиком
- ✅ Результаты против соперников по рейтингу

### 🌐 Веб-интерфейс
- ✅ Поиск и анализ любого игрока Lichess
- ✅ Адаптивный дизайн в стиле Lichess
- ✅ Темная тема
- ✅ Мобильная адаптация

### 🛠️ Командная строка
- ✅ Скрипты для управления БД
- ✅ Импорт из файлов и API
- ✅ Анализ дебютов
- ✅ Сравнение игроков

---

## 📁 Структура проекта

<pre>
lichess_db_project/
├── config/ # Конфигурационные файлы
│ ├── app_config.yaml # Общие настройки
│ ├── secrets.yaml # 🔒 Секреты (пароли, ключи) - не в git!
│ └── schemas/ # Схемы таблиц
│ └── v1_lichess_games.yaml
│
├── core/ # Ядро системы
│ ├── database/ # Работа с БД
│ │ ├── connection.py # Подключение (локальное/SSH)
│ │ ├── db_manager.py # Управление таблицами
│ │ └── schema_loader.py # Загрузчик схемы
│ ├── models/ # Модели данных
│ │ └── game.py # Модель шахматной партии
│ └── exceptions/ # Исключения
│
├── services/ # Сервисы
│ ├── pgn_parser.py # Парсер PGN файлов
│ ├── lichess_client.py # Клиент Lichess API
│ └── import_manager.py # Менеджер импорта
│
├── web_app/ # Веб-приложение
│ ├── static/ # CSS, JS
│ │ └── css/
│ │ └── style.css # Стили в стиле Lichess
│ ├── templates/ # HTML шаблоны
│ │ ├── base.html
│ │ ├── index.html
│ │ ├── player_stats.html
│ │ └── player_search.html
│ ├── app.py # Flask приложение
│ ├── config.py # Веб-конфигурация
│ └── routes.py # Маршруты
│
├── scripts/ # Исполняемые скрипты
│ ├── init_project.py # Инициализация проекта
│ ├── setup_db.py # Управление БД
│ ├── import_games.py # Импорт игр
│ ├── 01_analyze_games.py # Анализ игр
│ ├── 02_deep_analysis.py # Глубокий анализ
│ ├── 03_analyze_opening.py # Анализ дебютов
│ ├── 04_download_player_games.py # Скачивание игр игрока
│ ├── 05_analyze_player.py # Анализ игрока
│ └── 06_list_tables.py # Список таблиц
│
├── data/ # PGN файлы и данные
│ ├── downloads/ # Скачанные PGN
│ └── uploads/ # Загруженные PGN
│
├── tests/ # Тесты
├── logs/ # Логи
├── run_web.py # Запуск веб-приложения
├── requirements.txt # Зависимости
├── Makefile # Упрощение команд
└── README.md # Этот файл
</pre>


---

## 📋 Требования

- **Python** 3.8+
- **PostgreSQL** 12+
- **Lichess API токен** (опционально, для приватных игр)
- **pip** (менеджер пакетов Python)

---

## 🚀 Установка

### 1. Клонирование репозитория


git clone <repo-url>
cd lichess_db_project

2. Инициализация проекта
bash

# Создает виртуальное окружение и устанавливает зависимости
python3 scripts/init_project.py

# Или с пересозданием venv
python3 scripts/init_project.py --force-venv

3. Активация виртуального окружения
bash

source activate.sh

Или вручную:
bash

source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows

4. Установка зависимостей (если не установлены)
bash

pip install -r requirements.txt

⚙️ Настройка
1. Настройка секретов
bash

cp config/secrets.yaml.example config/secrets.yaml

Отредактируйте config/secrets.yaml:
yaml

# Локальная база данных
<pre>
local:
  host: "localhost"
  port: 5432
  user: "postgres"
  password: "your_password_here"
</pre>

# Lichess API токен (опционально)
<pre>
lichess:
  api_token: "lip_your_api_token_here"
  username: "your_lichess_username"
</pre>  

2. Настройка PostgreSQL

Убедитесь, что PostgreSQL запущен:
bash

sudo systemctl status postgresql  # Linux
# или
brew services list                 # Mac

Создайте базу данных (если нужно):
bash
<pre>
sudo -u postgres psql
CREATE DATABASE lichess_games;
CREATE USER your_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE lichess_games TO your_user;
\q
</pre>

📖 Использование
🗄️ Работа с базой данных
bash

# Создание таблицы
python3 scripts/setup_db.py --action create --verbose

# Просмотр статуса
python3 scripts/setup_db.py --action status --verbose

# Удаление таблицы
python3 scripts/setup_db.py --action drop --drop-table --verbose

# Пересоздание таблицы
python3 scripts/setup_db.py --action recreate --verbose

📥 Импорт игр
Из PGN файла
bash

# Импорт из файла
python3 scripts/import_games.py --source file --path data/uploads/games.pgn --player "YourName" --verbose

# Использование конфига
python3 scripts/import_games.py

Через Lichess API
bash

# Импорт последних 100 игр
python3 scripts/import_games.py --source api --username Hikaru --limit 100 --verbose

# Импорт за определенный период
python3 scripts/import_games.py --source api --username Hikaru --since 2024-01-01 --until 2024-12-31

# Только блиц игры
python3 scripts/import_games.py --source api --username Hikaru --perf-type blitz --limit 50

🌐 Веб-интерфейс
bash

# Запуск веб-приложения
python run_web.py

Откройте браузер: http://localhost:5000
Возможности веб-интерфейса:

    🔍 Поиск игрока — введите имя игрока Lichess

    📊 Статистика — игры, победы, рейтинг, дебюты

    📈 Графики — динамика рейтинга

    📱 Адаптивный дизайн — работает на телефонах

📊 Анализ игр

# Базовый анализ
python3 scripts/01_analyze_games.py

# Детальный анализ с графиками
python3 scripts/01_analyze_games.py --detailed

# Анализ игрока
python3 scripts/01_analyze_games.py --player "Hikaru"

# Глубокий анализ
<pre>
python3 scripts/02_deep_analysis.py
python3 scripts/02_deep_analysis.py --player "Hikaru"
</pre>

# Анализ дебютов
<pre>
python3 scripts/03_analyze_opening.py --list
python3 scripts/03_analyze_opening.py --player "Hikaru" --list
python3 scripts/03_analyze_opening.py --analyze "Caro-Kann Defense"
</pre>

# Скачивание игр игрока
<pre>
python3 scripts/04_download_player_games.py --username "Hikaru"
python3 scripts/04_download_player_games.py --username "Hikaru" --limit 100
</pre>

# Анализ игрока (отдельный скрипт)
python3 scripts/05_analyze_player.py --username "Hikaru"

# Список таблиц
python3 scripts/06_list_tables.py