#!/usr/bin/env python3
"""
Миграция 003: favorite_games -> game_annotations + is_favorite.

Идемпотентна. Существующие избранные становятся is_favorite=TRUE,
их заметки сохраняются.
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager
from core.database.migrations import annotations_table_status, ensure_annotations_table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--status', action='store_true')
    group.add_argument('--apply', action='store_true')
    parser.add_argument('--mode', '-m', choices=['local', 'remote'], default='local')
    parser.add_argument('--config', default='config/app_config.yaml')
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
    )
    db = DatabaseManager(ConfigLoader(args.config), args.mode)
    try:
        if args.status:
            status = annotations_table_status(db)
            print(f"\n📝 {status['table']}")
            print(f"  Существует: {'✅' if status['exists'] else '❌'}")
            if status['exists']:
                print(f"  Записей: {status['records']}")
                print(f"  Избранных: {status['favorites']}")
                print(f"  С заметками: {status['notes']}")
            return 0

        ensure_annotations_table(db)
        status = annotations_table_status(db)
        print(f"✅ {status['table']} готова: записей {status['records']}")
        return 0
    finally:
        db.close()


if __name__ == '__main__':
    sys.exit(main())
