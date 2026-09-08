.PHONY: init setup-db drop-db recreate-db status import import-file import-api clean test

# Переменные
PYTHON := python3
VENV := venv
PYTHON_VENV := $(VENV)/bin/python

init:
	@echo "🚀 Инициализация проекта..."
	$(PYTHON) scripts/init_project.py

setup-db:
	@echo "🗄️  Создание таблицы..."
	$(PYTHON_VENV) scripts/setup_db.py --action create $(ARGS)

drop-db:
	@echo "🗄️  Удаление таблицы..."
	$(PYTHON_VENV) scripts/setup_db.py --action drop --drop-table $(ARGS)

recreate-db:
	@echo "🗄️  Пересоздание таблицы..."
	$(PYTHON_VENV) scripts/setup_db.py --action recreate $(ARGS)

status:
	@echo "📊 Статус таблицы..."
	$(PYTHON_VENV) scripts/setup_db.py --action status --verbose

import-file:
	@echo "📥 Импорт из файла..."
	$(PYTHON_VENV) scripts/import_games.py --source file --path $(PATH) --player $(PLAYER) $(ARGS)

import-api:
	@echo "🌐 Импорт из API..."
	$(PYTHON_VENV) scripts/import_games.py --source api --username $(USERNAME) --limit $(LIMIT) $(ARGS)

import:
	@echo "📥 Импорт игр..."
	$(PYTHON_VENV) scripts/import_games.py $(ARGS)

test:
	@echo "🧪 Запуск тестов..."
	$(PYTHON_VENV) -m pytest tests/ -v

clean:
	@echo "🧹 Очистка..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf logs/*.log 2>/dev/null || true

# Примеры использования:
# make init
# make setup-db ARGS="--drop-table --verbose"
# make import-file PATH=data/uploads/games.pgn PLAYER=MyName
# make import-api USERNAME=my_lichess_name LIMIT=100
# make status
