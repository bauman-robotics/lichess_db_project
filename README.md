# Lichess Database Manager

Система для хранения и управления шахматными партиями с Lichess в PostgreSQL.

## 📁 Структура проекта
<pre>
lichess_db_project/
├── config/ # Конфигурационные файлы
│ ├── app_config.yaml # Общие настройки
│ ├── secrets.yaml # 🔒 Секреты (пароли, ключи) - не в git!
│ └── schemas/ # Схемы таблиц
├── core/ # Ядро системы
│ ├── database/ # Работа с БД
│ ├── models/ # Модели данных
│ └── exceptions/ # Исключения
├── services/ # Сервисы (импорт, парсинг)
├── scripts/ # Исполняемые скрипты
├── data/ # PGN файлы и данные
├── tests/ # Тесты
└── logs/ # Логи
</pre>


## 🚀 Быстрый старт

```bash
# 1. Клонирование
git clone <repo-url>
cd lichess_db_project

# 2. Инициализация проекта
python scripts/init_project.py

# 3. Активация виртуального окружения
source activate.sh

# 4. Настройка конфигов
cp config/secrets.yaml.example config/secrets.yaml
# Отредактируйте config/secrets.yaml

# 5. Создание таблицы
python scripts/setup_db.py --action create

📋 Требования

    Python 3.8+

    PostgreSQL 12+

    Lichess API токен (опционально)
