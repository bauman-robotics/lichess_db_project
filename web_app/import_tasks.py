"""
Очередь фонового импорта игр.

Задача хранится в import_tasks; один worker на процесс забирает queued-задачи.
Уникальные частичные индексы не дают запустить два импорта одновременно
и две активные задачи для одного игрока.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime
from typing import Optional

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager
from core.utils.lichess import normalize_lichess_username
from services.player_sync import fill_player_history, refresh_player_games

logger = logging.getLogger(__name__)

_worker_started = False
_worker_lock = threading.Lock()


def _get_db() -> DatabaseManager:
    return DatabaseManager(ConfigLoader(), 'local')


def create_import_task(username: str, mode: str = 'fill',
                       target_limit: int = 300) -> Optional[str]:
    """Ставит задачу в очередь. Возвращает task_id или None, если уже есть задача."""
    username = normalize_lichess_username(username).lower()
    mode = 'refresh' if mode == 'refresh' else 'fill'
    target_limit = max(1, int(target_limit))
    task_id = str(uuid.uuid4())

    db = _get_db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """
                        INSERT INTO import_tasks
                            (task_id, username, mode, target_limit, status)
                        VALUES (%s, %s, %s, %s, 'queued');
                        """,
                        (task_id, username, mode, target_limit),
                    )
                    conn.commit()
                    logger.info("Задача импорта %s добавлена: %s %s", task_id, username, mode)
                    return task_id
                except Exception as e:
                    conn.rollback()
                    logger.warning("Не удалось создать задачу импорта: %s", e)
                    return None
    finally:
        db.close()


def _claim_next_task() -> Optional[dict]:
    db = _get_db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH next AS (
                        SELECT task_id
                        FROM import_tasks
                        WHERE status = 'queued'
                        ORDER BY created_at
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE import_tasks AS t
                    SET status = 'running', started_at = NOW()
                    FROM next
                    WHERE t.task_id = next.task_id
                    RETURNING t.task_id, t.username, t.mode, t.target_limit;
                    """
                )
                row = cur.fetchone()
            conn.commit()
        if not row:
            return None
        return {
            'task_id': row[0],
            'username': row[1],
            'mode': row[2],
            'target_limit': row[3],
        }
    except Exception as e:
        logger.debug("Очередь импорта недоступна: %s", e)
        return None
    finally:
        db.close()


def get_import_task(task_id: str, username: Optional[str] = None) -> Optional[dict]:
    db = _get_db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                if username:
                    username = normalize_lichess_username(username).lower()
                    cur.execute(
                        """
                        SELECT task_id, username, mode, target_limit, status,
                               created_at, started_at, finished_at, saved, total, error
                        FROM import_tasks
                        WHERE task_id = %s AND lower(username) = %s;
                        """,
                        (task_id, username),
                    )
                else:
                    cur.execute(
                        """
                        SELECT task_id, username, mode, target_limit, status,
                               created_at, started_at, finished_at, saved, total, error
                        FROM import_tasks
                        WHERE task_id = %s;
                        """,
                        (task_id,),
                    )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    'task_id': row[0],
                    'username': row[1],
                    'mode': row[2],
                    'target_limit': row[3],
                    'status': row[4],
                    'created_at': row[5],
                    'started_at': row[6],
                    'finished_at': row[7],
                    'saved': row[8],
                    'total': row[9],
                    'error': row[10],
                }
    except Exception:
        return None
    finally:
        db.close()


def _finish_task(task_id: str, saved: int, total: int) -> None:
    db = _get_db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE import_tasks
                    SET status = 'done', finished_at = NOW(),
                        saved = %s, total = %s, error = NULL
                    WHERE task_id = %s;
                    """,
                    (saved, total, task_id),
                )
            conn.commit()
    finally:
        db.close()


def _fail_task(task_id: str, error: str) -> None:
    db = _get_db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE import_tasks
                    SET status = 'error', finished_at = NOW(), error = %s
                    WHERE task_id = %s;
                    """,
                    (error[:1000], task_id),
                )
            conn.commit()
    finally:
        db.close()


def cleanup_stale_tasks() -> None:
    db = _get_db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE import_tasks
                    SET status = 'error', finished_at = NOW(),
                        error = 'Задача прервана перезапуском сервиса'
                    WHERE status = 'running'
                      AND started_at < NOW() - INTERVAL '45 minutes';
                    """
                )
            conn.commit()
    except Exception:
        pass
    finally:
        db.close()


def _worker_loop() -> None:
    while True:
        try:
            task = _claim_next_task()
            if not task:
                time.sleep(3)
                continue

            logger.info("Старт импорта %s для %s", task['task_id'], task['username'])
            try:
                if task['mode'] == 'refresh':
                    result = refresh_player_games(
                        task['username'],
                        max_games=task['target_limit'],
                    )
                else:
                    result = fill_player_history(
                        task['username'],
                        target_limit=task['target_limit'],
                    )
                if result.get('success'):
                    _finish_task(
                        task['task_id'],
                        int(result.get('saved', 0) or 0),
                        int(result.get('total', 0) or 0),
                    )
                    logger.info("Импорт %s завершён: %s", task['task_id'], result.get('message'))
                else:
                    _fail_task(task['task_id'], result.get('error') or 'Неизвестная ошибка')
            except Exception as e:
                logger.exception("Ошибка импорта %s", task['task_id'])
                _fail_task(task['task_id'], str(e))
        except Exception as e:
            logger.warning("Ошибка worker-цикла импорта: %s", e)
            time.sleep(5)


def start_import_worker() -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True
    cleanup_stale_tasks()
    thread = threading.Thread(
        target=_worker_loop,
        name='import-worker',
        daemon=True,
    )
    thread.start()
    logger.info("Фоновый worker импорта запущен")
