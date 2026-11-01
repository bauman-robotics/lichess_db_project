#!/usr/bin/env python3
"""
Миграция 002: очередь фонового импорта import_tasks.

Идемпотентна.
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager
from core.database.migrations import ensure_import_tasks_table, import_tasks_status


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
            status = import_tasks_status(db)
            print(f"\n⏳ {status['table']}")
            print(f"  Существует: {'✅' if status['exists'] else '❌'}")
            if status['exists']:
                print(f"  В очереди: {status['queued']}")
                print(f"  Выполняется: {status['running']}")
            return 0

        ensure_import_tasks_table(db)
        status = import_tasks_status(db)
        print(f"✅ {status['table']} готова")
        return 0
    finally:
        db.close()


if __name__ == '__main__':
    sys.exit(main())
