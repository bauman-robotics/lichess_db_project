"""
Идемпотентные миграции схемы, не затрагивающие таблицы партий.

Сейчас единственная миграция — глобальная таблица избранного.
"""
from __future__ import annotations

import logging
from typing import Optional

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

FAVORITES_TABLE = "favorite_games"

CREATE_FAVORITES_SQL = f"""
CREATE TABLE IF NOT EXISTS {FAVORITES_TABLE} (
    player_username  VARCHAR(100) NOT NULL,
    game_id          VARCHAR(20)  NOT NULL,
    game_date        TIMESTAMP,
    opponent_name    VARCHAR(100),
    opponent_rating  INTEGER,
    player_color     VARCHAR(10),
    result           VARCHAR(10),
    opening_name     VARCHAR(200),
    time_control     VARCHAR(20),
    move_count       INTEGER,
    my_rating        INTEGER,
    game_url         VARCHAR(200),
    note             TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (player_username, game_id)
);
"""

CREATE_FAVORITES_INDEXES_SQL = f"""
CREATE INDEX IF NOT EXISTS idx_fav_created
    ON {FAVORITES_TABLE} (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fav_player
    ON {FAVORITES_TABLE} (player_username);
CREATE INDEX IF NOT EXISTS idx_fav_game_date
    ON {FAVORITES_TABLE} (game_date DESC);
"""


def _get_db(mode: str = "local") -> DatabaseManager:
    return DatabaseManager(ConfigLoader(), mode)


def ensure_favorites_table(db_manager: Optional[DatabaseManager] = None) -> bool:
    """
    Создаёт favorite_games и индексы, если их ещё нет.

    Безопасно вызывать повторно. Существующие таблицы партий не меняются.
    """
    db = db_manager or _get_db()
    own_db = db_manager is None
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                # Защита от гонки при нескольких воркерах/процессах.
                cur.execute("SELECT pg_advisory_xact_lock(20261022);")
                cur.execute(CREATE_FAVORITES_SQL)
                cur.execute(CREATE_FAVORITES_INDEXES_SQL)
            conn.commit()
        logger.info("Таблица %s готова", FAVORITES_TABLE)
        return True
    finally:
        if own_db:
            db.close()


def favorites_table_status(db_manager: Optional[DatabaseManager] = None) -> dict:
    """Возвращает состояние таблицы избранного для setup_db --action status."""
    db = db_manager or _get_db()
    own_db = db_manager is None
    status = {
        "table": FAVORITES_TABLE,
        "exists": False,
        "records": 0,
        "indexes": 0,
    }
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = %s;
                    """,
                    (FAVORITES_TABLE,),
                )
                status["exists"] = cur.fetchone() is not None
                if not status["exists"]:
                    return status

                cur.execute(f"SELECT COUNT(*) FROM {FAVORITES_TABLE};")
                status["records"] = int(cur.fetchone()[0] or 0)

                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM pg_indexes
                    WHERE schemaname = 'public' AND tablename = %s;
                    """,
                    (FAVORITES_TABLE,),
                )
                status["indexes"] = int(cur.fetchone()[0] or 0)
    finally:
        if own_db:
            db.close()
    return status
