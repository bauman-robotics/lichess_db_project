#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Работа с таблицей analysis_tasks — задачи анализа партий через DeepSeek.

Особенности:
  - глобальный лимит: не более 1 running-задачи одновременно
    (гарантируется частичным уникальным индексом в PostgreSQL);
  - задачи старше STALE_MINUTES помечаются как error;
  - при старте сервера все running-задачи становятся error
    (сервер перезапустился, старые воркеры мертвы).

Все функции работают через DatabaseManager и ту же БД lichess_games.
"""
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager


logger = logging.getLogger(__name__)


# Задача считается протухшей, если running дольше N минут
STALE_MINUTES = 10


# ============================================================
# ВСПОМОГАТЕЛЬНОЕ
# ============================================================

def _get_db() -> DatabaseManager:
    """Возвращает DatabaseManager для локальной БД."""
    config = ConfigLoader()
    return DatabaseManager(config, 'local')


# ============================================================
# СОЗДАНИЕ ЗАДАЧИ
# ============================================================

def create_task(username: str, game_id: str) -> Optional[str]:
    """
    Атомарно создаёт running-задачу.

    Возвращает task_id при успехе.
    Возвращает None, если уже есть running-задача (лимит 1).
    """
    task_id = str(uuid.uuid4())

    db = _get_db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                # Атомарная вставка. Если уже есть running-задача,
                # частичный уникальный индекс one_running_task вызовет ошибку.
                try:
                    cur.execute("""
                        INSERT INTO analysis_tasks
                            (task_id, username, game_id, status, started_at)
                        VALUES
                            (%s, %s, %s, 'running', NOW())
                    """, (task_id, username, game_id))
                    conn.commit()
                    logger.info(f"Создана задача {task_id} для {username}/{game_id}")
                    return task_id
                except Exception as e:
                    conn.rollback()
                    # Проверяем, не занят ли лимит
                    cur.execute("""
                        SELECT task_id, username, game_id
                        FROM analysis_tasks
                        WHERE status = 'running'
                        LIMIT 1
                    """)
                    row = cur.fetchone()
                    if row:
                        logger.warning(
                            f"Лимит занят: задача {row[0]} уже выполняется "
                            f"для {row[1]}/{row[2]}"
                        )
                    else:
                        logger.error(f"Ошибка создания задачи: {e}")
                    return None
    finally:
        db.close()


# ============================================================
# ЧТЕНИЕ
# ============================================================

def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """Возвращает задачу по ID или None."""
    db = _get_db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT task_id, username, game_id, status,
                           started_at, finished_at, error
                    FROM analysis_tasks
                    WHERE task_id = %s
                """, (task_id,))
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    'task_id': row[0],
                    'username': row[1],
                    'game_id': row[2],
                    'status': row[3],
                    'started_at': row[4],
                    'finished_at': row[5],
                    'error': row[6],
                }
    finally:
        db.close()


def get_running_task_for(username: str, game_id: str) -> Optional[Dict[str, Any]]:
    """Возвращает running-задачу для конкретной пары (username, game_id)."""
    db = _get_db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT task_id, username, game_id, status,
                           started_at, finished_at, error
                    FROM analysis_tasks
                    WHERE username = %s
                      AND game_id = %s
                      AND status = 'running'
                    LIMIT 1
                """, (username, game_id))
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    'task_id': row[0],
                    'username': row[1],
                    'game_id': row[2],
                    'status': row[3],
                    'started_at': row[4],
                    'finished_at': row[5],
                    'error': row[6],
                }
    finally:
        db.close()


def get_running_game_ids(username: str) -> List[str]:
    """
    Возвращает список game_id, для которых есть running-задача
    у указанного игрока. Используется для подкраски кнопок
    при рендере страницы.
    """
    db = _get_db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT game_id
                    FROM analysis_tasks
                    WHERE username = %s AND status = 'running'
                """, (username,))
                return [row[0] for row in cur.fetchall()]
    finally:
        db.close()


# ============================================================
# ОБНОВЛЕНИЕ
# ============================================================

def update_task_done(task_id: str):
    """Помечает задачу как выполненную."""
    db = _get_db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE analysis_tasks
                    SET status = 'done',
                        finished_at = NOW(),
                        error = NULL
                    WHERE task_id = %s
                """, (task_id,))
                conn.commit()
        logger.info(f"Задача {task_id} завершена")
    finally:
        db.close()


def update_task_error(task_id: str, error: str):
    """Помечает задачу как упавшую."""
    db = _get_db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE analysis_tasks
                    SET status = 'error', finished_at = NOW(), error = %s
                    WHERE task_id = %s
                """, (error[:1000], task_id))
                conn.commit()
        logger.warning(f"Задача {task_id} завершена с ошибкой: {error[:200]}")
    finally:
        db.close()


# ============================================================
# ОЧИСТКА ПРОТУХШИХ
# ============================================================

def cleanup_stale_tasks():
    """
    Помечает все running-задачи как error.
    Вызывается при старте сервера — после перезапуска
    старые воркеры мертвы, их задачи не могут завершиться.
    """
    db = _get_db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE analysis_tasks
                    SET status = 'error',
                        finished_at = NOW(),
                        error = 'Сервер перезапущен'
                    WHERE status = 'running'
                """)
                count = cur.rowcount
                conn.commit()
        if count > 0:
            logger.warning(f"Очищено {count} протухших задач при старте")
        else:
            logger.info("Протухших задач при старте нет")
    finally:
        db.close()


def cleanup_stale_running_task(task_id: str) -> bool:
    """
    Если задача старше STALE_MINUTES — помечает как error.
    Возвращает True, если задача была помечена как error.
    Используется при запросе статуса.
    """
    db = _get_db()
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                threshold = datetime.now() - timedelta(minutes=STALE_MINUTES)
                cur.execute("""
                    UPDATE analysis_tasks
                    SET status = 'error',
                        finished_at = NOW(),
                        error = 'Превышено время выполнения (%s минут)'
                    WHERE task_id = %s
                      AND status = 'running'
                      AND started_at < %s
                """, (STALE_MINUTES, task_id, threshold))
                updated = cur.rowcount > 0
                conn.commit()
                if updated:
                    logger.warning(
                        f"Задача {task_id} помечена как error "
                        f"(старше {STALE_MINUTES} минут)"
                    )
                return updated
    finally:
        db.close()