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

FAVORITES_TABLE = "favorite_games"  # legacy, до объединения
ANNOTATIONS_TABLE = "game_annotations"

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

CREATE_ANNOTATIONS_SQL = f"""
CREATE TABLE IF NOT EXISTS {ANNOTATIONS_TABLE} (
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
    is_favorite      BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (player_username, game_id)
);
"""

CREATE_ANNOTATIONS_INDEXES_SQL = f"""
CREATE INDEX IF NOT EXISTS idx_ann_created
    ON {ANNOTATIONS_TABLE} (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ann_player
    ON {ANNOTATIONS_TABLE} (player_username);
CREATE INDEX IF NOT EXISTS idx_ann_game_date
    ON {ANNOTATIONS_TABLE} (game_date DESC);
CREATE INDEX IF NOT EXISTS idx_ann_favorite
    ON {ANNOTATIONS_TABLE} (is_favorite) WHERE is_favorite;
CREATE INDEX IF NOT EXISTS idx_ann_note
    ON {ANNOTATIONS_TABLE} (updated_at DESC)
    WHERE note IS NOT NULL AND note <> '';
"""

IMPORT_TASKS_TABLE = "import_tasks"

CREATE_IMPORT_TASKS_SQL = f"""
CREATE TABLE IF NOT EXISTS {IMPORT_TASKS_TABLE} (
    task_id       VARCHAR(36) PRIMARY KEY,
    username      VARCHAR(100) NOT NULL,
    mode          VARCHAR(20)  NOT NULL DEFAULT 'fill',
    target_limit  INTEGER      NOT NULL DEFAULT 300,
    status        VARCHAR(20)  NOT NULL DEFAULT 'queued',
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    saved         INTEGER      NOT NULL DEFAULT 0,
    total         INTEGER      NOT NULL DEFAULT 0,
    error         TEXT
);
"""

CREATE_IMPORT_TASKS_INDEXES_SQL = f"""
CREATE UNIQUE INDEX IF NOT EXISTS one_running_import
    ON {IMPORT_TASKS_TABLE} (status) WHERE status = 'running';
CREATE UNIQUE INDEX IF NOT EXISTS one_active_import_per_player
    ON {IMPORT_TASKS_TABLE} (lower(username))
    WHERE status IN ('queued', 'running');
CREATE INDEX IF NOT EXISTS idx_import_tasks_created
    ON {IMPORT_TASKS_TABLE} (created_at);
"""


def _get_db(mode: str = "local") -> DatabaseManager:
    return DatabaseManager(ConfigLoader(), mode)


def ensure_annotations_table(db_manager: Optional[DatabaseManager] = None) -> bool:
    """
    Создаёт/обновляет game_annotations.

    Если есть старая favorite_games — переименовывает её и добавляет
    is_favorite=TRUE существующим избранным. Повторный запуск безопасен.
    """
    db = db_manager or _get_db()
    own_db = db_manager is None
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(20261024);")
                cur.execute(
                    "SELECT to_regclass('public.favorite_games'), "
                    "to_regclass('public.game_annotations');"
                )
                legacy, modern = cur.fetchone()

                if legacy and not modern:
                    cur.execute(
                        f'ALTER TABLE {FAVORITES_TABLE} RENAME TO {ANNOTATIONS_TABLE};'
                    )
                    logger.info("Таблица %s переименована в %s",
                                FAVORITES_TABLE, ANNOTATIONS_TABLE)

                cur.execute(CREATE_ANNOTATIONS_SQL)

                # Существующие строки были избранными. Новые — по умолчанию нет.
                cur.execute(
                    f"ALTER TABLE {ANNOTATIONS_TABLE} "
                    "ADD COLUMN IF NOT EXISTS is_favorite BOOLEAN NOT NULL DEFAULT TRUE;"
                )
                cur.execute(
                    f"ALTER TABLE {ANNOTATIONS_TABLE} "
                    "ALTER COLUMN is_favorite SET DEFAULT FALSE;"
                )
                cur.execute(CREATE_ANNOTATIONS_INDEXES_SQL)
            conn.commit()
        logger.info("Таблица %s готова", ANNOTATIONS_TABLE)
        return True
    finally:
        if own_db:
            db.close()


def ensure_favorites_table(db_manager: Optional[DatabaseManager] = None) -> bool:
    """Устаревшее имя; теперь создаёт game_annotations."""
    return ensure_annotations_table(db_manager)


def ensure_import_tasks_table(db_manager: Optional[DatabaseManager] = None) -> bool:
    """Создаёт import_tasks и индексы (идемпотентно)."""
    db = db_manager or _get_db()
    own_db = db_manager is None
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(20261023);")
                cur.execute(CREATE_IMPORT_TASKS_SQL)
                cur.execute(CREATE_IMPORT_TASKS_INDEXES_SQL)
            conn.commit()
        logger.info("Таблица %s готова", IMPORT_TASKS_TABLE)
        return True
    finally:
        if own_db:
            db.close()


def import_tasks_status(db_manager: Optional[DatabaseManager] = None) -> dict:
    """Краткий статус очереди импорта для setup_db --action status."""
    db = db_manager or _get_db()
    own_db = db_manager is None
    status = {"table": IMPORT_TASKS_TABLE, "exists": False, "queued": 0, "running": 0}
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = %s;
                    """,
                    (IMPORT_TASKS_TABLE,),
                )
                status["exists"] = cur.fetchone() is not None
                if not status["exists"]:
                    return status
                cur.execute(
                    f"SELECT status, COUNT(*) FROM {IMPORT_TASKS_TABLE} "
                    "WHERE status IN ('queued', 'running') GROUP BY status;"
                )
                for key, count in cur.fetchall():
                    status[key] = int(count)
    finally:
        if own_db:
            db.close()
    return status


def annotations_table_status(db_manager: Optional[DatabaseManager] = None) -> dict:
    """Состояние game_annotations для setup_db --action status."""
    db = db_manager or _get_db()
    own_db = db_manager is None
    status = {
        "table": ANNOTATIONS_TABLE,
        "exists": False,
        "records": 0,
        "favorites": 0,
        "notes": 0,
        "indexes": 0,
    }
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = %s;
                    """,
                    (ANNOTATIONS_TABLE,),
                )
                status["exists"] = cur.fetchone() is not None
                if not status["exists"]:
                    return status

                cur.execute(
                    f"SELECT COUNT(*), "
                    f"COUNT(*) FILTER (WHERE is_favorite), "
                    f"COUNT(*) FILTER (WHERE note IS NOT NULL AND note <> '') "
                    f"FROM {ANNOTATIONS_TABLE};"
                )
                row = cur.fetchone()
                status["records"] = int(row[0] or 0)
                status["favorites"] = int(row[1] or 0)
                status["notes"] = int(row[2] or 0)

                cur.execute(
                    """
                    SELECT COUNT(*) FROM pg_indexes
                    WHERE schemaname = 'public' AND tablename = %s;
                    """,
                    (ANNOTATIONS_TABLE,),
                )
                status["indexes"] = int(cur.fetchone()[0] or 0)
    finally:
        if own_db:
            db.close()
    return status


def favorites_table_status(db_manager: Optional[DatabaseManager] = None) -> dict:
    """Устаревшее имя; статус game_annotations."""
    return annotations_table_status(db_manager)


# ============================================================
# STOCKFISH: ОЦЕНКИ И ОЧЕРЕДЬ
# ============================================================

ENGINE_EVALS_TABLE = "game_engine_evals"
ENGINE_TASKS_TABLE = "engine_tasks"

CREATE_ENGINE_EVALS_SQL = f"""
CREATE TABLE IF NOT EXISTS {ENGINE_EVALS_TABLE} (
    player_username VARCHAR(100) NOT NULL,
    game_id         VARCHAR(20)  NOT NULL,
    ply             INTEGER      NOT NULL,
    san             VARCHAR(20),
    eval_cp         INTEGER,
    mate            INTEGER,
    depth           INTEGER      NOT NULL,
    engine          VARCHAR(50),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (player_username, game_id, ply)
);
"""

CREATE_ENGINE_EVALS_INDEXES_SQL = f"""
CREATE INDEX IF NOT EXISTS idx_engine_evals_game
    ON {ENGINE_EVALS_TABLE} (player_username, game_id);
"""

CREATE_ENGINE_TASKS_SQL = f"""
CREATE TABLE IF NOT EXISTS {ENGINE_TASKS_TABLE} (
    task_id         VARCHAR(36) PRIMARY KEY,
    player_username VARCHAR(100) NOT NULL,
    game_id         VARCHAR(20)  NOT NULL,
    depth           INTEGER      NOT NULL,
    status          VARCHAR(20)  NOT NULL DEFAULT 'queued',
    progress        INTEGER      NOT NULL DEFAULT 0,
    total           INTEGER      NOT NULL DEFAULT 0,
    error           TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ
);
"""

CREATE_ENGINE_TASKS_INDEXES_SQL = f"""
CREATE UNIQUE INDEX IF NOT EXISTS one_running_engine_task
    ON {ENGINE_TASKS_TABLE} (status) WHERE status = 'running';
CREATE UNIQUE INDEX IF NOT EXISTS one_active_engine_task_per_game
    ON {ENGINE_TASKS_TABLE} (player_username, game_id)
    WHERE status IN ('queued', 'running');
CREATE INDEX IF NOT EXISTS idx_engine_tasks_created
    ON {ENGINE_TASKS_TABLE} (created_at);
"""


def ensure_engine_tables(db_manager: Optional[DatabaseManager] = None) -> bool:
    """Создаёт game_engine_evals и engine_tasks (идемпотентно)."""
    db = db_manager or _get_db()
    own_db = db_manager is None
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(20261025);")
                cur.execute(CREATE_ENGINE_EVALS_SQL)
                cur.execute(CREATE_ENGINE_EVALS_INDEXES_SQL)
                cur.execute(CREATE_ENGINE_TASKS_SQL)
                cur.execute(CREATE_ENGINE_TASKS_INDEXES_SQL)
            conn.commit()
        logger.info("Таблицы движка готовы")
        return True
    finally:
        if own_db:
            db.close()


def engine_tables_status(db_manager: Optional[DatabaseManager] = None) -> dict:
    db = db_manager or _get_db()
    own_db = db_manager is None
    status = {
        "evals_table": ENGINE_EVALS_TABLE,
        "tasks_table": ENGINE_TASKS_TABLE,
        "exists": False,
        "evals": 0,
        "queued": 0,
        "running": 0,
    }
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT to_regclass(%s), to_regclass(%s);",
                    (f"public.{ENGINE_EVALS_TABLE}", f"public.{ENGINE_TASKS_TABLE}"),
                )
                evals, tasks = cur.fetchone()
                status["exists"] = bool(evals and tasks)
                if not status["exists"]:
                    return status
                cur.execute(f"SELECT COUNT(*) FROM {ENGINE_EVALS_TABLE};")
                status["evals"] = int(cur.fetchone()[0] or 0)
                cur.execute(
                    f"SELECT status, COUNT(*) FROM {ENGINE_TASKS_TABLE} "
                    "WHERE status IN ('queued','running') GROUP BY status;"
                )
                for key, count in cur.fetchall():
                    status[key] = int(count)
    finally:
        if own_db:
            db.close()
    return status


# ============================================================
# СТАДИИ АНАЛИЗА DEEPSEEK
# ============================================================

def ensure_analysis_task_columns(db_manager: Optional[DatabaseManager] = None) -> bool:
    """Добавляет stage/progress/total в analysis_tasks, если таблица есть."""
    db = db_manager or _get_db()
    own_db = db_manager is None
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.analysis_tasks');")
                if cur.fetchone()[0] is None:
                    return False
                cur.execute(
                    "ALTER TABLE analysis_tasks "
                    "ADD COLUMN IF NOT EXISTS stage VARCHAR(20) DEFAULT 'deepseek';"
                )
                cur.execute(
                    "ALTER TABLE analysis_tasks "
                    "ADD COLUMN IF NOT EXISTS progress INTEGER DEFAULT 0;"
                )
                cur.execute(
                    "ALTER TABLE analysis_tasks "
                    "ADD COLUMN IF NOT EXISTS total INTEGER DEFAULT 0;"
                )
            conn.commit()
        logger.info("Колонки стадий analysis_tasks готовы")
        return True
    finally:
        if own_db:
            db.close()
