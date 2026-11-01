"""
Синхронизация истории игрока: новые игры и догрузка более ранних.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager
from core.utils.lichess import player_table_name
from services.player_import import import_player_games


def get_game_counts(username: str, config: Optional[ConfigLoader] = None) -> dict:
    """Возвращает count/min_date/max_date для таблицы игрока."""
    config = config or ConfigLoader()
    db = DatabaseManager(config, 'local')
    original = db.table_name
    db.table_name = player_table_name(username)
    result = {'count': 0, 'min_date': None, 'max_date': None}
    try:
        if not db.table_exists():
            return result
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'SELECT COUNT(*), MIN(game_date), MAX(game_date) '
                    f'FROM "{db.table_name}";'
                )
                row = cur.fetchone()
                if row:
                    result = {
                        'count': int(row[0] or 0),
                        'min_date': row[1],
                        'max_date': row[2],
                    }
        return result
    finally:
        db.table_name = original
        db.close()


def fill_player_history(
    username: str,
    target_limit: int = 3000,
    config: Optional[ConfigLoader] = None,
) -> dict:
    """
    Догружает более ранние игры, пока в таблице не станет не меньше target_limit.

    Существующие игры не удаляются. Если игр уже достаточно — ничего не делает.
    """
    config = config or ConfigLoader()
    target_limit = max(1, int(target_limit))
    counts = get_game_counts(username, config)
    current = counts['count']

    if current >= target_limit:
        return {
            'success': True,
            'saved': 0,
            'total': 0,
            'message': f'В базе уже {current} игр — цель {target_limit} достигнута',
        }

    need = target_limit - current
    until = None
    if counts['min_date'] is not None:
        until = (counts['min_date'] - timedelta(days=1)).strftime('%Y-%m-%d')

    result = import_player_games(
        username,
        limit=need,
        config_loader=config,
        until=until,
        empty_ok=True,
    )
    if result.get('success'):
        saved = result.get('saved', 0)
        result['message'] = (
            f'Догружено {saved} более ранних игр (в базе было {current})'
            if saved else 'Более ранних игр не найдено'
        )
    return result


def refresh_player_games(
    username: str,
    max_games: int = 1000,
    config: Optional[ConfigLoader] = None,
) -> dict:
    """Догружает только новые игры (новее последней в базе)."""
    config = config or ConfigLoader()
    max_games = max(1, int(max_games))
    counts = get_game_counts(username, config)
    since = None
    if counts['max_date'] is not None:
        since = (counts['max_date'] - timedelta(days=1)).strftime('%Y-%m-%d')

    result = import_player_games(
        username,
        limit=max_games,
        config_loader=config,
        since=since,
        empty_ok=True,
    )
    if result.get('success'):
        saved = result.get('saved', 0)
        result['message'] = (
            f'Добавлено {saved} новых игр' if saved else 'Новых игр нет'
        )
    return result
