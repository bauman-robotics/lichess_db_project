"""Очередь фонового анализа Stockfish."""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Optional

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager
from core.utils.lichess import normalize_lichess_username
from services.engine_analysis import ensure_engine_evals, get_engine_config

logger = logging.getLogger(__name__)
_worker_started = False
_worker_lock = threading.Lock()


def _db():
    return DatabaseManager(ConfigLoader(), 'local')


def create_engine_task(username: str, game_id: str, depth: int) -> Optional[str]:
    config = ConfigLoader()
    if not get_engine_config(config)['enabled']:
        return None
    username = normalize_lichess_username(username).lower()
    task_id = str(uuid.uuid4())
    db = _db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """
                        INSERT INTO engine_tasks
                            (task_id, player_username, game_id, depth, status)
                        VALUES (%s, %s, %s, %s, 'queued');
                        """,
                        (task_id, username, game_id, int(depth)),
                    )
                    conn.commit()
                    return task_id
                except Exception as e:
                    conn.rollback()
                    logger.warning('Не удалось создать engine task: %s', e)
                    return None
    finally:
        db.close()


def get_engine_task(task_id: str, username: str, game_id: str) -> Optional[dict]:
    db = _db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT task_id, player_username, game_id, depth, status,
                           progress, total, error, created_at, started_at, finished_at
                    FROM engine_tasks
                    WHERE task_id = %s AND player_username = %s AND game_id = %s;
                    """,
                    (task_id, username.lower(), game_id),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    'task_id': row[0], 'username': row[1], 'game_id': row[2],
                    'depth': row[3], 'status': row[4], 'progress': row[5],
                    'total': row[6], 'error': row[7], 'created_at': row[8],
                    'started_at': row[9], 'finished_at': row[10],
                }
    except Exception:
        return None
    finally:
        db.close()


def get_active_engine_task(username: str, game_id: str) -> Optional[dict]:
    db = _db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT task_id, status, progress, total, depth
                    FROM engine_tasks
                    WHERE player_username = %s AND game_id = %s
                      AND status IN ('queued', 'running')
                    ORDER BY created_at DESC LIMIT 1;
                    """,
                    (username.lower(), game_id),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {'task_id': row[0], 'status': row[1], 'progress': row[2],
                        'total': row[3], 'depth': row[4]}
    except Exception:
        return None
    finally:
        db.close()


def _claim():
    db = _db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH next AS (
                        SELECT task_id FROM engine_tasks
                        WHERE status = 'queued'
                        ORDER BY created_at
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE engine_tasks AS t
                    SET status = 'running', started_at = NOW()
                    FROM next
                    WHERE t.task_id = next.task_id
                    RETURNING t.task_id, t.player_username, t.game_id, t.depth;
                    """
                )
                row = cur.fetchone()
            conn.commit()
        if not row:
            return None
        return {'task_id': row[0], 'username': row[1], 'game_id': row[2],
                'depth': row[3]}
    except Exception as e:
        logger.debug('engine queue unavailable: %s', e)
        return None
    finally:
        db.close()


def _progress(task_id: str, done: int, total: int) -> None:
    db = _db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'UPDATE engine_tasks SET progress = %s, total = %s WHERE task_id = %s;',
                    (done, total, task_id),
                )
            conn.commit()
    except Exception:
        pass
    finally:
        db.close()


def _finish(task_id: str, status: str, error: Optional[str] = None) -> None:
    db = _db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE engine_tasks
                    SET status = %s, finished_at = NOW(), error = %s
                    WHERE task_id = %s;
                    """,
                    (status, error, task_id),
                )
            conn.commit()
    finally:
        db.close()


def _cleanup() -> None:
    db = _db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE engine_tasks
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


def _loop() -> None:
    while True:
        task = _claim()
        if not task:
            time.sleep(3)
            continue
        try:
            ensure_engine_evals(
                task['username'], task['game_id'], task['depth'],
                progress_cb=lambda done, total: _progress(task['task_id'], done, total),
            )
            _finish(task['task_id'], 'done')
        except Exception as e:
            logger.exception('Engine task %s failed', task['task_id'])
            _finish(task['task_id'], 'error', str(e)[:1000])


def start_engine_worker() -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True
    _cleanup()
    threading.Thread(target=_loop, name='engine-worker', daemon=True).start()
    logger.info('Фоновый worker Stockfish запущен')
