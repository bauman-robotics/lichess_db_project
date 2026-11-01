"""
Импорт игр игрока с Lichess в его таблицу games_<username>.

Используется веб-маршрутом и CLI-скриптами импорта.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager
from core.database.schema_loader import SchemaLoader
from core.utils.lichess import normalize_lichess_username, player_table_name, safe_filename_part
from services.import_manager import ImportManager
from services.lichess_client import LichessClient

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS_DIR = PROJECT_ROOT / "data" / "downloads"


def _ensure_player_table(config: ConfigLoader, db: DatabaseManager, table_name: str) -> None:
    """Создаёт games_<username>, если её ещё нет."""
    if db.table_exists():
        return

    schema_loader = SchemaLoader(config.get_schema_path())
    schema = schema_loader.load()
    schema.table_name = table_name
    sql = schema_loader.get_create_table_sql(drop_existing=False)

    with db.connection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    logger.info("Таблица %s создана", table_name)


def import_player_games(
    username: str,
    limit: int = 1000,
    config_loader: Optional[ConfigLoader] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    empty_ok: bool = False,
) -> dict:
    """
    Скачивает игры игрока с Lichess и импортирует их.

    Args:
        since/until: необязательные границы (YYYY-MM-DD) для API.

    Returns:
        {'success': bool, 'saved': int, 'total': int, 'error': str|None}
    """
    config = config_loader or ConfigLoader()
    db: Optional[DatabaseManager] = None
    temp_file: Optional[Path] = None
    original_table = None

    try:
        username = normalize_lichess_username(username)
        table_name = player_table_name(username)

        lichess = LichessClient(config)
        pgn_content = lichess.download_games(
            username=username,
            max_games=limit,
            since=since,
            until=until,
        )
        if not pgn_content:
            if empty_ok:
                return {'success': True, 'error': None, 'saved': 0, 'total': 0,
                        'message': 'Игр не найдено'}
            return {'success': False, 'error': 'Не удалось загрузить игры',
                    'saved': 0, 'total': 0}

        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        temp_file = DOWNLOADS_DIR / f"{safe_filename_part(username)}_{timestamp}.pgn"
        temp_file.write_text(pgn_content, encoding='utf-8')

        db = DatabaseManager(config, 'local')
        original_table = db.table_name
        db.table_name = table_name
        _ensure_player_table(config, db, table_name)

        import_manager = ImportManager(config, db)
        result = import_manager.import_from_file(
            file_path=str(temp_file),
            player_name=username,
            delete_after_import=True,
        )
        temp_file = None

        return {
            'success': True,
            'saved': result.get('saved_games', 0),
            'total': result.get('total_parsed', 0),
            'error': None,
        }
    except Exception as e:
        logger.exception("Ошибка импорта игрока %s", username)
        return {'success': False, 'error': str(e), 'saved': 0, 'total': 0}
    finally:
        if db is not None:
            if original_table is not None:
                db.table_name = original_table
            db.close()
        if temp_file is not None and temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass
