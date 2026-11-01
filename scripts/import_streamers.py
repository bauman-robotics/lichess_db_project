#!/usr/bin/env python3
"""
Импорт игр стримеров из config/streamers.yaml.

Примеры:
  python scripts/import_streamers.py --dry-run
  python scripts/import_streamers.py
  python scripts/import_streamers.py --only RebeccaHarris,EricRosen
  python scripts/import_streamers.py --limit 300 --refresh
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager
from core.utils.lichess import player_table_name
from services.player_import import import_player_games
from services.streamers import load_streamer_config

logger = logging.getLogger("import_streamers")


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def player_table_exists(username: str, config_loader: ConfigLoader) -> bool:
    db = DatabaseManager(config_loader, "local")
    original = db.table_name
    db.table_name = player_table_name(username)
    try:
        return db.table_exists()
    finally:
        db.table_name = original
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Импорт игр стримеров")
    parser.add_argument("--config", default="config/streamers.yaml",
                        help="путь к списку стримеров")
    parser.add_argument("--app-config", default="config/app_config.yaml",
                        help="путь к app_config.yaml")
    parser.add_argument("--limit", type=int, default=None,
                        help="переопределить количество игр для всех")
    parser.add_argument("--only", default="",
                        help="только эти username через запятую")
    parser.add_argument("--refresh", action="store_true",
                        help="импортировать даже если таблица уже есть")
    parser.add_argument("--dry-run", action="store_true",
                        help="показать план без скачивания")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="пауза между стримерами, сек")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)
    config_loader = ConfigLoader(args.app_config)
    streamer_config = load_streamer_config(Path(args.config))
    streamers = streamer_config["streamers"]

    only = {
        value.strip().lower()
        for value in args.only.split(",")
        if value.strip()
    }
    if only:
        streamers = [
            item for item in streamers
            if item["username"].lower() in only
            or item["table_name"].lower() in only
        ]

    if not streamers:
        logger.warning("Нет стримеров для импорта")
        return 1

    logger.info("Стримеров к обработке: %s", len(streamers))
    succeeded = 0
    skipped = 0
    failed = 0

    for index, streamer in enumerate(streamers, start=1):
        username = streamer["username"]
        limit = args.limit if args.limit is not None else streamer["limit"]
        limit = max(1, int(limit))
        exists = player_table_exists(username, config_loader)

        prefix = f"[{index}/{len(streamers)}] {username} ({streamer['name']})"
        if exists and not args.refresh:
            logger.info("%s — уже загружен, пропуск", prefix)
            skipped += 1
            continue

        if args.dry_run:
            action = "обновить" if exists else "загрузить"
            logger.info("%s — %s, limit=%s", prefix, action, limit)
            continue

        logger.info("%s — импорт до %s игр...", prefix, limit)
        result = import_player_games(
            username,
            limit=limit,
            config_loader=config_loader,
        )
        if result.get("success"):
            logger.info(
                "%s — сохранено %s из %s",
                prefix,
                result.get("saved", 0),
                result.get("total", 0),
            )
            succeeded += 1
        else:
            logger.error("%s — ошибка: %s", prefix, result.get("error"))
            failed += 1

        if args.delay and index < len(streamers):
            time.sleep(args.delay)

    logger.info(
        "Итог: успешно %s, пропущено %s, ошибок %s",
        succeeded, skipped, failed,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
