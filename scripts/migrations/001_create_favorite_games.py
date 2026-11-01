#!/usr/bin/env python3
"""
Миграция 001: глобальная таблица избранных партий favorite_games.

Идемпотентна: повторный запуск не меняет данные и не падает.

Примеры:
  python scripts/migrations/001_create_favorite_games.py --status
  python scripts/migrations/001_create_favorite_games.py --apply
  python scripts/migrations/001_create_favorite_games.py --apply --mode remote
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager
from core.database.migrations import (
    ensure_favorites_table,
    favorites_table_status,
)


def setup_logging(verbose: bool = False):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--status', action='store_true', help='Показать состояние таблицы')
    group.add_argument('--apply', action='store_true', help='Создать таблицу и индексы')
    parser.add_argument('--mode', '-m', choices=['local', 'remote'], default='local')
    parser.add_argument('--config', default='config/app_config.yaml')
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()

    setup_logging(args.verbose)
    db = DatabaseManager(ConfigLoader(args.config), args.mode)

    try:
        if args.status:
            status = favorites_table_status(db)
            print(f"\n⭐ {status['table']}")
            print(f"  Существует: {'✅' if status['exists'] else '❌'}")
            if status['exists']:
                print(f"  Записей: {status['records']}")
                print(f"  Индексов: {status['indexes']}")
            return 0

        ensure_favorites_table(db)
        status = favorites_table_status(db)
        print(f"✅ {status['table']} готова, записей: {status['records']}")
        return 0
    finally:
        db.close()


if __name__ == '__main__':
    sys.exit(main())
