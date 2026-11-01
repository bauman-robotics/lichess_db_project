"""
Маршруты веб-приложения
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import date, datetime, time as dt_time, timedelta
import json
import re
import time
import uuid
import threading
import logging
from collections import Counter
from math import ceil
from typing import Optional
from urllib.parse import urlencode

import chess
import chess.pgn
from io import StringIO

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort, make_response
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SelectField, SubmitField

from wtforms.validators import DataRequired, Optional, NumberRange, ValidationError

# Импортируем существующие сервисы
from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager
from core.utils.lichess import (
    LichessUsernameError,
    SPEED_LABELS,
    classify_time_control,
    normalize_lichess_username,
    player_table_name,
    time_control_speed_sql,
)
from services.lichess_client import LichessClient
from services.import_manager import ImportManager
from services.pgn_parser import PGNParser
from services.player_import import import_player_games
from services.streamers import get_streamer_cards, streamer_table_names

from web_app import tasks as analysis_tasks
from web_app.import_tasks import create_import_task, get_import_task
from services.deepseek_analyzer import analyze_game, check_health, DeepSeekError, DeepSeekUnavailable, clean_pgn

main_bp = Blueprint('main', __name__)

# Формы
def validate_lichess_username(form, field):
    """Нормализует имя или ссылку на профиль Lichess до чистого имени."""
    try:
        field.data = normalize_lichess_username(field.data)
    except LichessUsernameError as e:
        raise ValidationError(str(e))


class PlayerSearchForm(FlaskForm):
    username = StringField(
        'Имя игрока или ссылка на профиль',
        validators=[DataRequired(), validate_lichess_username],
    )
    limit = SelectField('Количество игр', 
                        choices=[
                            ('100', '100 игр'),
                            ('500', '500 игр'),
                            ('1000', '1000 игр'),
                            ('5000', '5000 игр'),
                            ('10000', 'Все игры (до 10000)')
                        ],
                        default='1000',
                        validators=[DataRequired()])
    submit = SubmitField('Анализировать')

def get_safe_table_name(username: str) -> str:
    """Возвращает безопасное имя таблицы для использования в SQL"""
    return player_table_name(username)


_KNOWN_PLAYERS_CACHE = {'ts': 0.0, 'data': []}
_KNOWN_PLAYERS_TTL = 10


def get_known_players(limit: Optional[int] = 8, force: bool = False) -> list:
    """
    Список игроков, для которых в базе есть таблица games_<username>.

    Возвращает [{'username', 'table_name', 'games', 'last_game', 'featured'}],
    избранный игрок первым, остальные — по дате последней игры.
    """
    now = time.monotonic()
    if not force and (now - _KNOWN_PLAYERS_CACHE['ts']) < _KNOWN_PLAYERS_TTL:
        data = _KNOWN_PLAYERS_CACHE['data']
        return data if limit is None else data[:limit]

    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    streamer_tables = streamer_table_names()
    players = []

    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name LIKE 'games\\_%' ESCAPE '\\'
                    ORDER BY table_name;
                    """
                )
                tables = [row[0] for row in cur.fetchall()]

                configured_username = config.get('secrets.lichess.username')
                featured_username = (
                    config.get('ui.featured_player') or configured_username
                )
                configured_table = (
                    get_safe_table_name(configured_username)
                    if configured_username
                    else None
                )

                for table in tables:
                    if not re.fullmatch(r'games_[a-z0-9_]+', table):
                        continue
                    try:
                        cur.execute(
                            f'SELECT COUNT(*), MAX(game_date) FROM "{table}";'
                        )
                        games_count, last_game = cur.fetchone()
                    except Exception as e:
                        db.logger.warning(f"Не удалось прочитать {table}: {e}")
                        conn.rollback()
                        continue

                    display_name = (
                        configured_username
                        if configured_table == table
                        else table[len('games_'):]
                    )
                    players.append({
                        'username': display_name,
                        'table_name': table,
                        'games': int(games_count or 0),
                        'last_game': last_game,
                        'is_streamer': table in streamer_tables,
                        'featured': bool(
                            featured_username
                            and display_name.lower() == str(featured_username).lower()
                        ),
                    })
    except Exception as e:
        db.logger.warning(f"Не удалось получить список игроков: {e}")
        players = []
    finally:
        db.close()

    players.sort(
        key=lambda p: (
            0 if p['featured'] else 1,
            -(p['last_game'].toordinal() if p['last_game'] else 0),
        ),
    )
    _KNOWN_PLAYERS_CACHE['ts'] = now
    _KNOWN_PLAYERS_CACHE['data'] = players
    return players if limit is None else players[:limit]


# ============================================================
# ИЗБРАННОЕ
# ============================================================

FAVORITES_TABLE = 'favorite_games'
NOTE_MAX_LENGTH = 2000


def get_favorites_count() -> int:
    """Общее количество избранных партий (для счётчика в шапке)."""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f'SELECT COUNT(*) FROM {FAVORITES_TABLE};')
                return int(cur.fetchone()[0] or 0)
    except Exception:
        # Таблицы может ещё не быть до миграции — счётчик просто 0.
        return 0
    finally:
        db.close()


def get_favorite_ids(username: str, game_ids: list) -> set:
    """Множество game_id, которые уже в избранном у игрока."""
    if not game_ids:
        return set()
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT game_id
                    FROM {FAVORITES_TABLE}
                    WHERE player_username = %s AND game_id = ANY(%s);
                    """,
                    (username.lower(), list(game_ids)),
                )
                return {row[0] for row in cur.fetchall()}
    except Exception:
        return set()
    finally:
        db.close()


def get_game_snapshot(username: str, game_id: str) -> Optional[dict]:
    """Метаданные партии для снимка в избранном."""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    table_name = get_safe_table_name(username)
    original_table = db.table_name
    db.table_name = table_name
    if not db.table_exists():
        db.table_name = original_table
        db.close()
        return None

    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        game_date, opponent_name, opponent_rating, player_color,
                        result, opening_name, time_control, move_count,
                        my_rating, game_url
                    FROM "{table_name}"
                    WHERE game_id = %s
                    LIMIT 1;
                    """,
                    (game_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    'player_username': username.lower(),
                    'game_id': game_id,
                    'game_date': row[0],
                    'opponent_name': row[1],
                    'opponent_rating': row[2],
                    'player_color': row[3],
                    'result': row[4],
                    'opening_name': row[5],
                    'time_control': row[6],
                    'move_count': row[7],
                    'my_rating': row[8],
                    'game_url': row[9],
                }
    finally:
        db.table_name = original_table
        db.close()


def add_favorite(username: str, game_id: str) -> Optional[int]:
    """
    Добавляет партию в избранное (идемпотентно).

    Returns:
        Новое количество избранного или None, если партия не найдена.
    """
    snapshot = get_game_snapshot(username, game_id)
    if not snapshot:
        return None

    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO {FAVORITES_TABLE} (
                        player_username, game_id, game_date, opponent_name,
                        opponent_rating, player_color, result, opening_name,
                        time_control, move_count, my_rating, game_url
                    ) VALUES (
                        %(player_username)s, %(game_id)s, %(game_date)s,
                        %(opponent_name)s, %(opponent_rating)s, %(player_color)s,
                        %(result)s, %(opening_name)s, %(time_control)s,
                        %(move_count)s, %(my_rating)s, %(game_url)s
                    )
                    ON CONFLICT (player_username, game_id) DO NOTHING;
                    """,
                    snapshot,
                )
                cur.execute(f'SELECT COUNT(*) FROM {FAVORITES_TABLE};')
                count = int(cur.fetchone()[0] or 0)
            conn.commit()
        return count
    finally:
        db.close()


def remove_favorite(username: str, game_id: str) -> int:
    """Удаляет партию из избранного, возвращает новый счётчик."""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'DELETE FROM {FAVORITES_TABLE} '
                    'WHERE player_username = %s AND game_id = %s;',
                    (username.lower(), game_id),
                )
                cur.execute(f'SELECT COUNT(*) FROM {FAVORITES_TABLE};')
                count = int(cur.fetchone()[0] or 0)
            conn.commit()
        return count
    finally:
        db.close()


def update_favorite_note(username: str, game_id: str, note: str) -> bool:
    """Обновляет заметку к избранной партии."""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE {FAVORITES_TABLE}
                    SET note = %s, updated_at = NOW()
                    WHERE player_username = %s AND game_id = %s;
                    """,
                    (note[:NOTE_MAX_LENGTH], username.lower(), game_id),
                )
                updated = cur.rowcount > 0
            conn.commit()
        return updated
    finally:
        db.close()


def get_favorites(q: str = '', sort: str = 'added', page: int = 1,
                  per_page: int = 25, username: Optional[str] = None):
    """
    Глобальный список избранного с поиском и пагинацией.

    Returns:
        tuple[list[dict], int]
    """
    where = []
    params = []

    normalized_username = username.lower() if username else None
    if normalized_username:
        where.append('player_username = %s')
        params.append(normalized_username)

    if q:
        like = f'%{q}%'
        where.append(
            '(player_username ILIKE %s OR opponent_name ILIKE %s '
            'OR opening_name ILIKE %s OR note ILIKE %s)'
        )
        params.extend([like, like, like, like])

    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''
    order_sql = {
        'added': 'created_at DESC, player_username, game_id',
        'game_date': 'game_date DESC NULLS LAST, created_at DESC',
        'opponent': 'opponent_name ASC NULLS LAST, created_at DESC',
    }.get(sort, 'created_at DESC, player_username, game_id')

    page = max(1, int(page or 1))
    per_page = max(1, int(per_page or 25))
    offset = (page - 1) * per_page

    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    items = []
    total = 0
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'SELECT COUNT(*) FROM {FAVORITES_TABLE} {where_sql};',
                    params,
                )
                total = int(cur.fetchone()[0] or 0)

                cur.execute(
                    f"""
                    SELECT
                        player_username, game_id, game_date, opponent_name,
                        opponent_rating, player_color, result, opening_name,
                        time_control, move_count, my_rating, game_url,
                        note, created_at, updated_at
                    FROM {FAVORITES_TABLE}
                    {where_sql}
                    ORDER BY {order_sql}
                    LIMIT %s OFFSET %s;
                    """,
                    params + [per_page, offset],
                )
                for row in cur.fetchall():
                    items.append({
                        'player_username': row[0],
                        'game_id': row[1],
                        'date': row[2],
                        'opponent': row[3],
                        'opponent_rating': row[4],
                        'color': row[5],
                        'result': row[6],
                        'opening': row[7],
                        'time_control': row[8],
                        'move_count': row[9],
                        'my_rating': row[10],
                        'game_url': row[11],
                        'note': row[12] or '',
                        'created_at': row[13],
                        'updated_at': row[14],
                    })
    except Exception as e:
        db.logger.warning(f'Не удалось прочитать избранное: {e}')
    finally:
        db.close()

    return items, total


def count_games_vs_opponent(username: str, opponent: str) -> int:
    """Количество партий игрока против указанного соперника."""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    table_name = player_table_name(username)
    original_table = db.table_name
    db.table_name = table_name
    try:
        if not db.table_exists():
            return 0
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'SELECT COUNT(*) FROM "{table_name}" '
                    'WHERE opponent_name ILIKE %s;',
                    (f'%{opponent}%',),
                )
                return int(cur.fetchone()[0] or 0)
    except Exception as e:
        db.logger.warning(f'Не удалось посчитать игры с {opponent}: {e}')
        return 0
    finally:
        db.table_name = original_table
        db.close()


def get_player_stats(username: str) -> dict:
    """Получает статистику игрока из таблицы игрока"""
    print(f"🔍 DEBUG: get_player_stats вызвана для {username}")
    
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    
    table_name = get_safe_table_name(username)
    original_table = db.table_name
    db.table_name = table_name
    
    # Проверяем существование таблицы
    if not db.table_exists():
        db.table_name = original_table
        db.close()
        print(f"❌ DEBUG: Таблица {table_name} не существует")
        return {'exists': False, 'error': f'Таблица {table_name} не существует'}
    
    print(f"✅ DEBUG: Таблица {table_name} существует")
    
    # Получаем статистику
    stats = db.get_table_stats()
    db.table_name = original_table
    db.close()
    
    print(f"📊 DEBUG: stats = {stats}")
    
    # Проверяем, есть ли данные
    if not stats or stats.get('total_records', 0) == 0:
        return {
            'exists': True,
            'total': 0,
            'first_game': None,
            'last_game': None,
            'opponents': 0,
            'accuracy': 0,
            'results': {},
            'empty': True
        }
    
    # Формируем результат
    result_dist = {}
    for result, count in stats.get('results_distribution', []):
        result_dist[result] = count
    
    # Получаем точность, если есть
    accuracy = stats.get('avg_accuracy')
    if accuracy is None:
        # Пробуем вычислить вручную
        try:
            with db.connection.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT AVG(accuracy) FROM {table_name} WHERE accuracy IS NOT NULL")
                    accuracy = cur.fetchone()[0]
        except:
            accuracy = None
    
    result = {
        'exists': True,
        'total': stats.get('total_records', 0),
        'first_game': stats.get('first_game'),
        'last_game': stats.get('last_game'),
        'opponents': stats.get('unique_opponents', 0),
        'accuracy': accuracy if accuracy is not None else 0,
        'results': result_dist
    }
    
    print(f"✅ DEBUG: get_player_stats результат = {result}")
    return result


def get_opening_stats(username: str, limit: int = 30) -> list:
    """Получает статистику по дебютам из таблицы игрока"""
    print(f"🔍 DEBUG: get_opening_stats вызвана для {username}")
    
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    
    table_name = get_safe_table_name(username)
    original_table = db.table_name
    db.table_name = table_name
    
    if not db.table_exists():
        db.table_name = original_table
        db.close()
        return []
    
    results = []
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT 
                        opening_name,
                        COUNT(*) as games,
                        SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN result = 'Loss' THEN 1 ELSE 0 END) as losses,
                        SUM(CASE WHEN result = 'Draw' THEN 1 ELSE 0 END) as draws,
                        ROUND(AVG(accuracy), 1) as avg_accuracy
                    FROM {table_name}
                    WHERE opening_name IS NOT NULL AND opening_name != ''
                    GROUP BY opening_name
                    HAVING COUNT(*) >= 1
                    ORDER BY games DESC
                    LIMIT %s;
                """, (limit,))
                
                for row in cur.fetchall():
                    name = str(row[0]).strip() if row[0] else 'Неизвестно'
                    games = int(row[1]) if row[1] is not None else 0
                    wins = int(row[2]) if row[2] is not None else 0
                    losses = int(row[3]) if row[3] is not None else 0
                    draws = int(row[4]) if row[4] is not None else 0
                    accuracy = float(row[5]) if row[5] is not None else 0
                    win_rate = (wins / games * 100) if games > 0 else 0
                    
                    results.append({
                        'name': name,
                        'games': games,
                        'wins': wins,
                        'losses': losses,
                        'draws': draws,
                        'accuracy': accuracy,
                        'win_rate': win_rate
                    })
    except Exception as e:
        print(f"❌ ERROR in get_opening_stats: {e}")
        import traceback
        traceback.print_exc()
    
    db.table_name = original_table
    db.close()
    
    print(f"✅ DEBUG: get_opening_stats вернула {len(results)} дебютов")
    return results


def get_recent_games(username: str, limit: int = 10) -> list:
    """Получает последние игры игрока из таблицы игрока"""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    
    table_name = get_safe_table_name(username)
    original_table = db.table_name
    db.table_name = table_name
    
    if not db.table_exists():
        db.table_name = original_table
        db.close()
        return []
    
    with db.connection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT 
                    game_id,
                    game_date,
                    player_color,
                    opponent_name,
                    result,
                    accuracy,
                    move_count,
                    opening_name,
                    my_rating,
                    opponent_rating,
                    game_analysis
                FROM {table_name}
                ORDER BY game_date DESC, id DESC
                LIMIT %s;
            """, (limit,))
            
            results = []
            for row in cur.fetchall():
                results.append({
                    'game_id': row[0],
                    'date': row[1],
                    'color': row[2],
                    'opponent': row[3],
                    'result': row[4],
                    'accuracy': row[5],
                    'move_count': row[6],
                    'opening': row[7],
                    'my_rating': row[8],
                    'opponent_rating': row[9],
                    'analysis': row[10] or ''
                })
    
    db.table_name = original_table
    db.close()
    return results

def get_game_for_analysis(username: str, game_id: str) -> dict:
    """
    Загружает партию из БД для анализа.
    Возвращает словарь или None, если партия не найдена.
    """
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    table_name = get_safe_table_name(username)
    original_table = db.table_name
    db.table_name = table_name

    if not db.table_exists():
        db.table_name = original_table
        db.close()
        return None

    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT
                        game_id, game_date, player_color, opponent_name,
                        opponent_rating, result, opening_name, time_control,
                        move_count, pgn_moves, game_analysis
                    FROM {table_name}
                    WHERE game_id = %s;
                """, (game_id,))
                row = cur.fetchone()
                if not row:
                    return None
                game = {
                    'game_id': row[0],
                    'game_date': row[1],
                    'color': row[2],
                    'opponent_name': row[3],
                    'opponent_rating': row[4],
                    'result': row[5],
                    'opening_name': row[6],
                    'time_control': row[7],
                    'move_count': row[8],
                    'pgn_moves': row[9] or '',
                    'game_analysis': row[10] or '',
                }
                game['is_favorite'] = game_id in get_favorite_ids(username, [game_id])
                return game
    finally:
        db.table_name = original_table
        db.close()

def _game_meta(game: dict) -> dict:
    """
    Формирует словарь метаданных партии для модалки.
    Используется в JSON-ответах POST /analyze и GET /analyze/status.
    """
    if not game:
        return {}
    return {
        'date': game['game_date'].strftime('%d.%m.%Y') if game.get('game_date') else '—',
        'color': game.get('color', '—'),
        'opponent': game.get('opponent_name', '—'),
        'opponent_rating': game.get('opponent_rating', ''),
        'result': game.get('result', '—'),
        'opening': game.get('opening_name') or '—',
        'time_control': game.get('time_control') or '—',
    }
    
def save_analysis(username: str, game_id: str, analysis: str) -> bool:
    """Сохраняет текст анализа в поле game_analysis."""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    table_name = get_safe_table_name(username)
    original_table = db.table_name
    db.table_name = table_name

    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE {table_name} SET game_analysis = %s WHERE game_id = %s",
                    (analysis, game_id)
                )
                conn.commit()
        return True
    except Exception as e:
        print(f"❌ Ошибка сохранения анализа: {e}")
        return False
    finally:
        db.table_name = original_table
        db.close()

def _run_analysis_task(task_id: str, username: str, game_id: str):
    """
    Выполняется в фоновом потоке.
    Загружает партию, вызывает DeepSeek, сохраняет результат.
    """
    logger = logging.getLogger(__name__)
    try:
        logger.info(f"[task {task_id}] Старт анализа {username}/{game_id}")

        # 1. Загружаем партию
        game = get_game_for_analysis(username, game_id)
        if not game:
            raise DeepSeekError(f"Партия {game_id} не найдена")

        # 2. Вызываем DeepSeek
        analysis = analyze_game(game, player_name=username)
        logger.info(f"[task {task_id}] Ответ получен, {len(analysis)} символов")

        # 3. Сохраняем в БД
        if not save_analysis(username, game_id, analysis):
            raise DeepSeekError("Не удалось сохранить анализ в БД")

        # 4. Помечаем задачу как done
        analysis_tasks.update_task_done(task_id)
        logger.info(f"[task {task_id}] Завершено успешно")

    except DeepSeekUnavailable as e:
        msg = f"DeepSeek недоступен: {e}"
        logger.error(f"[task {task_id}] {msg}")
        analysis_tasks.update_task_error(task_id, msg)

    except DeepSeekError as e:
        msg = f"Ошибка DeepSeek: {e}"
        logger.error(f"[task {task_id}] {msg}")
        analysis_tasks.update_task_error(task_id, msg)

    except Exception as e:
        msg = f"Неожиданная ошибка: {e}"
        logger.exception(f"[task {task_id}] {msg}")
        analysis_tasks.update_task_error(task_id, msg)

def get_games_filtered(
    username,
    opening=None,
    results=None,
    color=None,
    date_from=None,
    date_to=None,
    opponent=None,
    speed=None,
    page=1,
    per_page=50,
):
    """
    Выборка игр игрока по фильтрам.

    Args:
        username: имя игрока
        opening: подстрока названия дебюта (ILIKE %...%), или None
        results: список ['Win', 'Loss', 'Draw'], или None (все)
        color: 'white' / 'black' / None (оба)
        date_from: datetime.date или None — включительно
        date_to: datetime.date или None — включительно
        opponent: подстрока имени соперника, или None
        speed: категория контроля (blitz/rapid/...), или None
        page: номер страницы (1-based)
        per_page: размер страницы

    Returns:
        tuple[list[dict], int]: (игры, общее количество по фильтрам)
    """
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')

    table_name = get_safe_table_name(username)
    original_table = db.table_name
    db.table_name = table_name

    if not db.table_exists():
        db.table_name = original_table
        db.close()
        return [], 0

    where = []
    params = []

    if opening:
        where.append("opening_name ILIKE %s")
        params.append(f"%{opening}%")

    if results:
        placeholders = ','.join(['%s'] * len(results))
        where.append(f"result IN ({placeholders})")
        params.extend(results)

    if color:
        where.append("player_color = %s")
        params.append(color)

    if date_from:
        where.append("game_date >= %s")
        params.append(datetime.combine(date_from, dt_time.min))

    if date_to:
        where.append("game_date < %s")
        params.append(datetime.combine(date_to + timedelta(days=1), dt_time.min))

    if opponent:
        where.append("opponent_name ILIKE %s")
        params.append(f"%{opponent}%")

    if speed:
        where.append(f"({time_control_speed_sql('time_control')}) = %s")
        params.append(speed)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    page = max(1, int(page or 1))
    per_page = max(1, int(per_page or 50))
    offset = (page - 1) * per_page

    count_sql = f'SELECT COUNT(*) FROM "{table_name}" {where_sql};'
    data_sql = f"""
        SELECT
            game_id,
            game_date,
            my_rating,
            time_control,
            player_color,
            move_count,
            opponent_name,
            opponent_rating,
            result,
            opening_name,
            game_url,
            game_analysis
        FROM "{table_name}"
        {where_sql}
        ORDER BY game_date DESC, id DESC
        LIMIT %s OFFSET %s;
    """

    results_list = []
    total = 0
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(count_sql, params)
                total = int(cur.fetchone()[0] or 0)

                cur.execute(data_sql, params + [per_page, offset])
                for r in cur.fetchall():
                    results_list.append({
                        'game_id': r[0],
                        'date': r[1],
                        'my_rating': r[2],
                        'time_control': r[3],
                        'color': r[4],
                        'move_count': r[5],
                        'opponent': r[6],
                        'opponent_rating': r[7],
                        'result': r[8],
                        'opening': r[9],
                        'game_url': r[10],
                        'analysis': r[11] or '',
                    })
    except Exception as e:
        print(f"❌ Ошибка get_games_filtered: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.table_name = original_table
        db.close()

    return results_list, total

def get_rating_stats(username: str) -> dict:
    """Получает статистику по рейтингу"""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    
    table_name = get_safe_table_name(username)
    original_table = db.table_name
    db.table_name = table_name
    
    if not db.table_exists():
        db.table_name = original_table
        db.close()
        return {}
    
    with db.connection.get_connection() as conn:
        with conn.cursor() as cur:
            # Общая статистика
            cur.execute(f"""
                SELECT 
                    AVG(my_rating) as avg_rating,
                    MIN(my_rating) as min_rating,
                    MAX(my_rating) as max_rating,
                    AVG(opponent_rating) as avg_opp_rating
                FROM {table_name}
                WHERE my_rating > 0 AND opponent_rating > 0
            """)
            row = cur.fetchone()
            
            # Статистика по контролю времени с текущим рейтингом
            cur.execute(f"""
                WITH ranked_games AS (
                    SELECT 
                        time_control,
                        my_rating,
                        opponent_rating,
                        result,
                        game_date,
                        ROW_NUMBER() OVER (PARTITION BY time_control ORDER BY game_date DESC) as rn
                    FROM {table_name}
                    WHERE my_rating > 0 AND opponent_rating > 0
                ),
                time_stats AS (
                    SELECT 
                        time_control,
                        AVG(my_rating) as avg_rating,
                        MIN(my_rating) as min_rating,
                        MAX(my_rating) as max_rating,
                        AVG(opponent_rating) as avg_opp_rating,
                        COUNT(*) as games,
                        SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins
                    FROM {table_name}
                    WHERE my_rating > 0 AND opponent_rating > 0
                    GROUP BY time_control
                ),
                last_ratings AS (
                    SELECT 
                        time_control,
                        my_rating as last_rating,
                        game_date as last_game_date
                    FROM ranked_games
                    WHERE rn = 1
                )
                SELECT 
                    ts.time_control,
                    ts.avg_rating,
                    ts.min_rating,
                    ts.max_rating,
                    ts.avg_opp_rating,
                    ts.games,
                    ts.wins,
                    lr.last_rating,
                    lr.last_game_date
                FROM time_stats ts
                LEFT JOIN last_ratings lr ON ts.time_control = lr.time_control
                ORDER BY ts.games DESC
            """)
            
            rating_by_time = []
            for r in cur.fetchall():
                rating_by_time.append({
                    'time_control': r[0] if r[0] else 'Неизвестно',
                    'avg_rating': r[1] if r[1] else 0,
                    'min_rating': r[2] if r[2] else 0,
                    'max_rating': r[3] if r[3] else 0,
                    'avg_opponent_rating': r[4] if r[4] else 0,
                    'games': r[5] if r[5] else 0,
                    'wins': r[6] if r[6] else 0,
                    'last_rating': r[7] if r[7] else 0,
                    'last_game_date': r[8] if r[8] else None,
                    'win_rate': (r[6] / r[5] * 100) if r[5] and r[5] > 0 else 0
                })
            
            # Распределение по рейтингу соперников
            cur.execute(f"""
                SELECT 
                    CASE 
                        WHEN opponent_rating > my_rating + 100 THEN 'Сильнее на 100+'
                        WHEN opponent_rating > my_rating THEN 'Сильнее'
                        WHEN opponent_rating < my_rating - 100 THEN 'Слабее на 100+'
                        WHEN opponent_rating < my_rating THEN 'Слабее'
                        ELSE 'Равный'
                    END as category,
                    COUNT(*) as games,
                    SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins
                FROM {table_name}
                WHERE my_rating > 0 AND opponent_rating > 0
                GROUP BY category
            """)
            
            rating_results = []
            for r in cur.fetchall():
                rating_results.append({
                    'category': r[0],
                    'games': r[1],
                    'wins': r[2],
                    'win_rate': (r[2] / r[1] * 100) if r[1] > 0 else 0
                })
    
    db.table_name = original_table
    db.close()
    
    return {
        'avg_rating': row[0] if row and row[0] else 0,
        'min_rating': row[1] if row and row[1] else 0,
        'max_rating': row[2] if row and row[2] else 0,
        'avg_opponent_rating': row[3] if row and row[3] else 0,
        'by_time_control': rating_by_time,
        'by_category': rating_results
    }


def get_time_control_stats(username: str) -> list:
    """Статистика по контролю времени"""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    
    table_name = get_safe_table_name(username)
    original_table = db.table_name
    db.table_name = table_name
    
    if not db.table_exists():
        db.table_name = original_table
        db.close()
        return []
    
    with db.connection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT 
                    time_control,
                    COUNT(*) as games,
                    SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins,
                    ROUND(AVG(accuracy), 1) as avg_accuracy
                FROM {table_name}
                GROUP BY time_control
                ORDER BY games DESC
                LIMIT 10
            """)
            
            results = []
            for row in cur.fetchall():
                results.append({
                    'time_control': row[0],
                    'games': row[1],
                    'wins': row[2],
                    'win_rate': (row[2] / row[1] * 100) if row[1] > 0 else 0,
                    'accuracy': row[3] if row[3] else 0
                })
    
    db.table_name = original_table
    db.close()
    return results


def get_speed_categories(username: str) -> tuple[list, str | None]:
    """
    Категории контроля с количеством игр и категория последней партии.

    Returns:
        (categories, last_speed)
    """
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    table_name = get_safe_table_name(username)
    original_table = db.table_name
    db.table_name = table_name
    categories = []
    last_speed = None

    if not db.table_exists():
        db.table_name = original_table
        db.close()
        return categories, last_speed

    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                speed_sql = time_control_speed_sql('time_control')
                cur.execute(f"""
                    SELECT {speed_sql} AS speed, COUNT(*)
                    FROM "{table_name}"
                    GROUP BY 1
                    ORDER BY COUNT(*) DESC, 1;
                """)
                for key, count in cur.fetchall():
                    if key in SPEED_LABELS:
                        categories.append({
                            'key': key,
                            'label': SPEED_LABELS[key],
                            'games': int(count),
                        })

                cur.execute(f"""
                    SELECT time_control
                    FROM "{table_name}"
                    ORDER BY game_date DESC, id DESC
                    LIMIT 1;
                """)
                row = cur.fetchone()
                if row:
                    last_speed = classify_time_control(row[0])
    except Exception as e:
        print(f"❌ Ошибка get_speed_categories: {e}")
    finally:
        db.table_name = original_table
        db.close()

    return categories, last_speed


def get_rating_progression(
    username: str,
    speed: str | None = None,
    date_from=None,
    limit: int | None = None,
) -> list:
    """Прогресс рейтинга с дебютами, с фильтром по категории и дате."""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    
    table_name = get_safe_table_name(username)
    original_table = db.table_name
    db.table_name = table_name
    
    if not db.table_exists():
        db.table_name = original_table
        db.close()
        return []
    
    where = []
    params = []
    if speed:
        where.append(f"({time_control_speed_sql('time_control')}) = %s")
        params.append(speed)
    if date_from:
        where.append("game_date >= %s")
        params.append(datetime.combine(date_from, dt_time.min))

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    limit_sql = "LIMIT %s" if limit else ""
    if limit:
        params.append(limit)

    results = []
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT 
                        game_date,
                        COALESCE(my_rating, 0) as my_rating,
                        COALESCE(opponent_rating, 0) as opponent_rating,
                        COALESCE(result, '—') as result,
                        COALESCE(opening_name, '—') as opening_name,
                        COALESCE(player_color, '—') as player_color,
                        COALESCE(time_control, '—') as time_control,
                        game_id
                    FROM "{table_name}"
                    {where_sql}
                    ORDER BY game_date DESC, id DESC
                    {limit_sql}
                """, params)
                
                for row in cur.fetchall():
                    date_val = row[0]
                    if isinstance(date_val, datetime):
                        date_str = date_val.strftime('%Y-%m-%d')
                    elif date_val:
                        date_str = str(date_val)
                    else:
                        date_str = '2000-01-01'
                    
                    results.append({
                        'date': date_str,
                        'my_rating': int(row[1]) if row[1] is not None else 0,
                        'opponent_rating': int(row[2]) if row[2] is not None else 0,
                        'result': str(row[3]) if row[3] else '—',
                        'opening': str(row[4]) if row[4] else '—',
                        'color': str(row[5]) if row[5] else '—',
                        'time_control': str(row[6]) if row[6] else '—',
                        'game_id': str(row[7]) if row[7] else '',
                    })
    except Exception as e:
        print(f"❌ ERROR in get_rating_progression: {e}")
        import traceback
        traceback.print_exc()
    
    db.table_name = original_table
    db.close()
    
    return results


def get_move_stats(username: str) -> dict:
    """Статистика по длине партий + топ-10 коротких/длинных."""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')

    table_name = get_safe_table_name(username)
    original_table = db.table_name
    db.table_name = table_name

    if not db.table_exists():
        db.table_name = original_table
        db.close()
        return {}

    with db.connection.get_connection() as conn:
        with conn.cursor() as cur:
            # Общая статистика
            cur.execute(f"""
                SELECT 
                    AVG(move_count) as avg_moves,
                    MIN(move_count) as min_moves,
                    MAX(move_count) as max_moves,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY move_count) as median_moves
                FROM {table_name}
            """)
            row = cur.fetchone()

            # Распределение по длине
            cur.execute(f"""
                SELECT 
                    CASE 
                        WHEN move_count < 20 THEN 'Короткие (1-19)'
                        WHEN move_count < 40 THEN 'Средние (20-39)'
                        WHEN move_count < 60 THEN 'Длинные (40-59)'
                        ELSE 'Очень длинные (60+)'
                    END as category,
                    COUNT(*) as games,
                    SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins
                FROM {table_name}
                GROUP BY category
            """)
            distribution = []
            for r in cur.fetchall():
                distribution.append({
                    'category': r[0],
                    'games': r[1],
                    'wins': r[2],
                    'win_rate': (r[2] / r[1] * 100) if r[1] > 0 else 0
                })

            # Топ-10 коротких партий
            cur.execute(f"""
                SELECT 
                    game_id, game_date, opponent_name, opponent_rating,
                    player_color, result, move_count, opening_name, time_control
                FROM {table_name}
                WHERE move_count IS NOT NULL AND move_count > 0
                ORDER BY move_count ASC
                LIMIT 10
            """)
            shortest = []
            for r in cur.fetchall():
                shortest.append({
                    'game_id': r[0],
                    'date': r[1],
                    'opponent': r[2],
                    'opponent_rating': r[3],
                    'color': r[4],
                    'result': r[5],
                    'move_count': r[6],
                    'full_moves': (r[6] + 1) // 2 if r[6] else 0,
                    'opening': r[7],
                    'time_control': r[8],
                })

            # Топ-10 длинных партий
            cur.execute(f"""
                SELECT 
                    game_id, game_date, opponent_name, opponent_rating,
                    player_color, result, move_count, opening_name, time_control
                FROM {table_name}
                WHERE move_count IS NOT NULL AND move_count > 0
                ORDER BY move_count DESC
                LIMIT 10
            """)
            longest = []
            for r in cur.fetchall():
                longest.append({
                    'game_id': r[0],
                    'date': r[1],
                    'opponent': r[2],
                    'opponent_rating': r[3],
                    'color': r[4],
                    'result': r[5],
                    'move_count': r[6],
                    'full_moves': (r[6] + 1) // 2 if r[6] else 0,
                    'opening': r[7],
                    'time_control': r[8],
                })

    db.table_name = original_table
    db.close()

    return {
        'avg_moves': row[0] if row else 0,
        'min_moves': row[1] if row else 0,
        'max_moves': row[2] if row else 0,
        'median_moves': row[3] if row else 0,
        'distribution': distribution,
        'shortest': shortest,
        'longest': longest,
    }

def download_player_games(username: str, limit: int = 1000) -> dict:
    """Скачивает игры игрока с Lichess и сохраняет в таблицу игрока."""
    result = import_player_games(username, limit=limit)
    if result.get('success'):
        _KNOWN_PLAYERS_CACHE['ts'] = 0.0
    return result

def get_popular_openings() -> list:
    """
    Читает список популярных дебютов из config/openings.yaml.

    Возвращает список строк. Если файл отсутствует или пуст — пустой список.
    """
    import yaml
    from pathlib import Path

    path = Path(__file__).parent.parent / 'config' / 'openings.yaml'
    if not path.exists():
        print(f"⚠️  Файл дебютов не найден: {path}")
        return []

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        openings = data.get('openings', []) if data else []
        return openings if isinstance(openings, list) else []
    except Exception as e:
        print(f"❌ Ошибка чтения openings.yaml: {e}")
        return []

def get_known_players_ui(limit=None) -> list:
    """Список игроков для UI с учётом флага show_known_players."""
    config = ConfigLoader()
    if not config.get('ui.show_known_players', True):
        return []
    return get_known_players(limit=limit)


def get_known_players_limit() -> int:
    config = ConfigLoader()
    try:
        return max(1, int(config.get('ui.known_players_limit', 8)))
    except (TypeError, ValueError):
        return 8


def render_search_page(form):
    all_players = get_known_players_ui()
    known_players = [
        player for player in all_players if not player.get('is_streamer')
    ][:get_known_players_limit()]
    streamers = get_streamer_cards(all_players) if all_players else []
    return render_template(
        'player_search.html',
        form=form,
        known_players=known_players,
        streamers=streamers,
    )


@main_bp.route('/favorites')
def favorites_list():
    """Глобальный список избранных партий с поиском."""
    q = request.args.get('q', '').strip()
    sort = request.args.get('sort', 'added').strip()
    if sort not in ('added', 'game_date', 'opponent'):
        sort = 'added'

    try:
        per_page = int(request.args.get('per_page', 25))
    except (TypeError, ValueError):
        per_page = 25
    if per_page not in (25, 50, 100):
        per_page = 25

    page = max(1, request.args.get('page', 1, type=int) or 1)
    items, total = get_favorites(q=q, sort=sort, page=page, per_page=per_page)
    pages = max(1, ceil(total / per_page)) if total else 1
    if page > pages:
        page = pages
        items, total = get_favorites(q=q, sort=sort, page=page, per_page=per_page)

    query_params = []
    if q:
        query_params.append(('q', q))
    if sort != 'added':
        query_params.append(('sort', sort))
    if per_page != 25:
        query_params.append(('per_page', str(per_page)))

    page_numbers = list(range(1, pages + 1))
    page_links = [
        {
            'number': number,
            'url': '?' + urlencode(query_params + [('page', number)]),
            'active': number == page,
        }
        for number in page_numbers
    ]
    per_page_links = [
        {
            'size': size,
            'url': '?' + urlencode(
                [p for p in query_params if p[0] != 'per_page']
                + [('per_page', size)]
            ),
            'active': size == per_page,
        }
        for size in (25, 50, 100)
    ]
    prev_url = (
        '?' + urlencode(query_params + [('page', page - 1)])
        if page > 1 else None
    )
    next_url = (
        '?' + urlencode(query_params + [('page', page + 1)])
        if page < pages else None
    )

    return render_template(
        'favorites.html',
        favorites=items,
        total=total,
        page=page,
        pages=pages,
        per_page=per_page,
        page_links=page_links,
        per_page_links=per_page_links,
        prev_url=prev_url,
        next_url=next_url,
        q=q,
        sort=sort,
    )


def _favorite_payload():
    data = request.get_json(silent=True) or {}
    raw_username = data.get('player_username') or data.get('username')
    game_id = str(data.get('game_id') or '').strip()
    try:
        username = normalize_lichess_username(raw_username)
    except LichessUsernameError as e:
        return None, None, (jsonify({'error': str(e)}), 400)
    if not re.fullmatch(r'[A-Za-z0-9]{1,20}', game_id):
        return None, None, (jsonify({'error': 'Неверный game_id'}), 400)
    return username, game_id, None


@main_bp.route('/favorites', methods=['POST'])
def favorites_add():
    """Добавляет партию в избранное (AJAX)."""
    username, game_id, error = _favorite_payload()
    if error:
        return error
    try:
        count = add_favorite(username, game_id)
    except Exception as e:
        return jsonify({'error': f'Избранное недоступно: {e}'}), 503
    if count is None:
        return jsonify({'error': 'Партия не найдена'}), 404
    return jsonify({'favorited': True, 'count': count})


@main_bp.route('/favorites/<username>/<game_id>', methods=['DELETE'])
def favorites_remove(username, game_id):
    """Удаляет партию из избранного (AJAX)."""
    try:
        username = normalize_lichess_username(username)
    except LichessUsernameError as e:
        return jsonify({'error': str(e)}), 400
    try:
        count = remove_favorite(username, game_id)
    except Exception as e:
        return jsonify({'error': f'Избранное недоступно: {e}'}), 503
    return jsonify({'favorited': False, 'count': count})


@main_bp.route('/favorites/<username>/<game_id>', methods=['PATCH'])
def favorites_note(username, game_id):
    """Обновляет заметку к избранной партии (AJAX)."""
    try:
        username = normalize_lichess_username(username)
    except LichessUsernameError as e:
        return jsonify({'error': str(e)}), 400
    data = request.get_json(silent=True) or {}
    note = str(data.get('note') or '')
    if len(note) > NOTE_MAX_LENGTH:
        return jsonify({'error': f'Заметка длиннее {NOTE_MAX_LENGTH} символов'}), 400
    try:
        updated = update_favorite_note(username, game_id, note)
    except Exception as e:
        return jsonify({'error': f'Избранное недоступно: {e}'}), 503
    if not updated:
        return jsonify({'error': 'Партия не найдена в избранном'}), 404
    return jsonify({'ok': True, 'note': note})


@main_bp.route('/')
def index():
    """Главная страница"""
    all_players = get_known_players_ui()
    known_players = [
        player for player in all_players if not player.get('is_streamer')
    ][:get_known_players_limit()]
    return render_template('index.html', known_players=known_players)

@main_bp.route('/about')
def about():
    """Страница с описанием проекта и видеопрезентацией."""
    return render_template('about.html')

@main_bp.route('/search', methods=['GET', 'POST'])
def search():
    """Поиск игрока с автоматическим скачиванием"""
    form = PlayerSearchForm()
    
    if form.validate_on_submit():
        username = form.username.data.strip()
        limit = int(form.limit.data)
        
        stats = get_player_stats(username)
        
        if not stats.get('exists'):
            flash(f'⏳ Загрузка игр для {username}... Это может занять несколько секунд.', 'info')
            result = download_player_games(username, limit=limit)
            
            if result.get('success'):
                flash(f'✅ Загружено {result["saved"]} игр для {username}', 'success')
            else:
                flash(f'❌ Ошибка загрузки: {result.get("error", "Неизвестная ошибка")}', 'danger')
                return render_search_page(form)
        
        return redirect(f'/lichess-analyzer/player/{username}')
    
    return render_search_page(form)

@main_bp.route('/player/<username>')
def player_stats(username):
    """Страница статистики игрока: последние игры + базовая статистика."""
    # Получаем лимит из URL (если есть)
    limit = request.args.get('limit', 1000, type=int)

    stats = get_player_stats(username)

    if not stats.get('exists'):
        flash(f'Игрок {username} не найден. Скачиваем игры...', 'info')
        result = download_player_games(username, limit=limit)

        if result.get('success'):
            flash(f'✅ Загружено {result["saved"]} игр для {username}', 'success')
            return redirect(f'/lichess-analyzer/player/{username}')
        else:
            flash(f'❌ Ошибка загрузки: {result.get("error")}', 'danger')
            return render_template('player_stats.html',
                                   username=username,
                                   stats=None,
                                   exists=False,
                                   games=[],
                                   favorite_ids=[],
                                   current_section='games')

    # Лимит последних игр из конфига
    config_loader = ConfigLoader()
    recent_limit = config_loader.get('statistics.recent_games_limit', 25)
    games = get_recent_games(username, limit=recent_limit)
    favorite_ids = get_favorite_ids(username, [g['game_id'] for g in games])

    featured_player = (
        config_loader.get('ui.featured_player')
        or config_loader.get('secrets.lichess.username')
    )
    featured_is_current = bool(
        featured_player and str(featured_player).lower() == username.lower()
    )
    featured_games_count = 0
    if featured_player and not featured_is_current:
        featured_games_count = count_games_vs_opponent(username, str(featured_player))

    # Конфиг просмотрщика партии
    _default_tab = (config_loader.get('viewer.default_tab', 'comments') or 'comments').lower()
    if _default_tab not in ('moves', 'comments'):
        _default_tab = 'comments'

    viewer_config = {
        'board_size_desktop': config_loader.get('viewer.board_size_desktop', 500),
        'board_size_mobile':  config_loader.get('viewer.board_size_mobile', 320),
        'play_interval_ms':   config_loader.get('viewer.play_interval_ms', 800),
        'default_tab':        _default_tab,
        'show_coords':        bool(config_loader.get('viewer.show_coords', True)),
    }

    return render_template('player_stats.html',
                           username=username,
                           stats=stats,
                           exists=True,
                           games=games,
                           favorite_ids=favorite_ids,
                           featured_player=featured_player,
                           featured_is_current=featured_is_current,
                           featured_games_count=featured_games_count,
                           import_task_id=request.args.get('import_task'),
                           viewer_config=viewer_config,
                           current_section='games')

@main_bp.route('/player/<username>/refresh', methods=['POST'])
def player_refresh(username):
    """Ставит в очередь обновление истории или догрузку старых игр."""
    action = request.form.get('action', 'refresh')
    mode = 'refresh' if action == 'refresh' else 'fill'
    try:
        target_limit = int(request.form.get('target_limit', 300))
    except (TypeError, ValueError):
        target_limit = 300
    if target_limit not in (300, 1000, 3000):
        target_limit = 300

    task_id = create_import_task(username, mode=mode, target_limit=target_limit)
    if not task_id:
        flash('⚠️ Для этого игрока уже есть задача импорта. Дождитесь её завершения.', 'warning')
        return redirect(f'/lichess-analyzer/player/{username}')

    action_label = 'обновление новых игр' if mode == 'refresh' else f'догрузка до {target_limit}'
    flash(f'⏳ Задача добавлена в очередь: {action_label}.', 'info')
    return redirect(f'/lichess-analyzer/player/{username}?import_task={task_id}')


@main_bp.route('/player/<username>/import/status/<task_id>')
def import_status(username, task_id):
    """JSON-статус фоновой задачи импорта."""
    task = get_import_task(task_id, username)
    if not task:
        return jsonify({'error': 'Задача не найдена'}), 404

    for key in ('created_at', 'started_at', 'finished_at'):
        value = task.get(key)
        task[key] = value.isoformat() if value else None
    return jsonify(task)

@main_bp.route('/player/<username>/delete', methods=['POST'])
def delete_player(username):
    """Удаляет таблицу игрока"""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')

    table_name = get_safe_table_name(username)
    original_table = db.table_name
    db.table_name = table_name

    try:
        if db.table_exists():
            db.drop_table()
            try:
                with db.connection.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            'DELETE FROM favorite_games WHERE player_username = %s;',
                            (username.lower(),),
                        )
                    conn.commit()
            except Exception as fav_error:
                db.logger.warning(f'Не удалось очистить избранное игрока: {fav_error}')
            flash(f'🗑️ Таблица игрока {username} удалена', 'success')
        else:
            flash(f'Таблица {username} не найдена', 'warning')
    except Exception as e:
        flash(f'❌ Ошибка удаления: {e}', 'danger')
    finally:
        db.table_name = original_table
        db.close()
        _KNOWN_PLAYERS_CACHE['ts'] = 0.0

    return redirect(f'/lichess-analyzer/')  

def _parse_filter_date(value: str):
    """Парсит YYYY-MM-DD; возвращает date или None."""
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


@main_bp.route('/player/<username>/openings')
def player_openings(username):
    """Страница анализа партий по дебютам с фильтрами и пагинацией."""
    opening = request.args.get('opening', '').strip()
    results = request.args.getlist('result') or None
    color = request.args.get('color', '').strip() or None
    opponent = request.args.get('opponent', '').strip() or None
    speed = request.args.get('speed', '').strip() or None
    if speed not in SPEED_LABELS:
        speed = None

    date_from_raw = request.args.get('date_from', '').strip()
    date_to_raw = request.args.get('date_to', '').strip()
    date_from = _parse_filter_date(date_from_raw)
    date_to = _parse_filter_date(date_to_raw)
    date_error = None

    if date_from_raw and date_from is None:
        date_error = 'Дата начала указана в неверном формате (нужно ГГГГ-ММ-ДД).'
    elif date_to_raw and date_to is None:
        date_error = 'Дата окончания указана в неверном формате (нужно ГГГГ-ММ-ДД).'
    elif date_from and date_to and date_from > date_to:
        date_error = 'Дата начала позже даты окончания — фильтр по датам не применён.'
        date_from = None
        date_to = None

    config_loader = ConfigLoader()
    try:
        default_per_page = int(config_loader.get('statistics.debuts_per_page', 50))
    except (TypeError, ValueError):
        default_per_page = 50
    if default_per_page not in (25, 50, 100):
        default_per_page = 50

    per_page = request.args.get('per_page', default_per_page, type=int)
    if per_page not in (25, 50, 100):
        per_page = default_per_page

    page = max(1, request.args.get('page', 1, type=int) or 1)

    games, total = get_games_filtered(
        username,
        opening=opening or None,
        results=results,
        color=color,
        date_from=date_from,
        date_to=date_to,
        opponent=opponent,
        speed=speed,
        page=page,
        per_page=per_page,
    )

    pages = max(1, ceil(total / per_page)) if total else 1
    if page > pages:
        page = pages
        games, total = get_games_filtered(
            username,
            opening=opening or None,
            results=results,
            color=color,
            date_from=date_from,
            date_to=date_to,
            opponent=opponent,
            speed=speed,
            page=page,
            per_page=per_page,
        )

    # Параметры без page — для пагинации и ссылок «популярные дебюты».
    query_params = []
    if opening:
        query_params.append(('opening', opening))
    for result in (results or []):
        query_params.append(('result', result))
    if color:
        query_params.append(('color', color))
    if opponent:
        query_params.append(('opponent', opponent))
    if speed:
        query_params.append(('speed', speed))
    if date_from_raw and date_from:
        query_params.append(('date_from', date_from_raw))
    if date_to_raw and date_to:
        query_params.append(('date_to', date_to_raw))
    if per_page != default_per_page:
        query_params.append(('per_page', str(per_page)))

    base_query = urlencode(query_params)

    def url_without(key: str) -> str:
        remaining = [(k, v) for k, v in query_params if k != key]
        return '?' + urlencode(remaining)

    active_filters = []
    if opening:
        active_filters.append({
            'label': f'Дебют: {opening}',
            'url': url_without('opening'),
        })
    if opponent:
        active_filters.append({
            'label': f'Соперник: {opponent}',
            'url': url_without('opponent'),
        })
    if speed:
        active_filters.append({
            'label': f'Контроль: {SPEED_LABELS[speed]}',
            'url': url_without('speed'),
        })
    if color:
        color_label = 'белые' if color == 'white' else 'чёрные'
        active_filters.append({
            'label': f'Цвет: {color_label}',
            'url': url_without('color'),
        })
    if results:
        active_filters.append({
            'label': 'Результат: ' + ', '.join(results),
            'url': url_without('result'),
        })
    if date_from:
        active_filters.append({
            'label': f'С даты: {date_from.strftime("%d.%m.%Y")}',
            'url': url_without('date_from'),
        })
    if date_to:
        active_filters.append({
            'label': f'По дату: {date_to.strftime("%d.%m.%Y")}',
            'url': url_without('date_to'),
        })

    page_links = []
    if pages <= 9:
        page_numbers = list(range(1, pages + 1))
    elif page <= 5:
        page_numbers = [1, 2, 3, 4, 5, 6, 7, None, pages]
    elif page >= pages - 4:
        page_numbers = [1, None] + list(range(pages - 6, pages + 1))
    else:
        page_numbers = [1, None, page - 2, page - 1, page, page + 1, page + 2, None, pages]

    for number in page_numbers:
        if number is None:
            page_links.append({'number': None, 'url': None, 'active': False})
            continue
        page_links.append({
            'number': number,
            'url': '?' + urlencode(query_params + [('page', number)]),
            'active': number == page,
        })

    per_page_links = []
    for size in (25, 50, 100):
        per_page_links.append({
            'size': size,
            'url': '?' + urlencode(
                [p for p in query_params if p[0] != 'per_page']
                + [('per_page', size)]
            ),
            'active': size == per_page,
        })

    prev_url = (
        '?' + urlencode(query_params + [('page', page - 1)])
        if page > 1 else None
    )
    next_url = (
        '?' + urlencode(query_params + [('page', page + 1)])
        if page < pages else None
    )

    popular_openings = get_popular_openings()
    speed_categories, _ = get_speed_categories(username)
    favorite_ids = get_favorite_ids(username, [g['game_id'] for g in games])

    # Задачи в статусе running — чтобы подкрасить кнопки жёлтым при загрузке
    running_ids = analysis_tasks.get_running_game_ids(username)

    _default_tab = (config_loader.get('viewer.default_tab', 'comments') or 'comments').lower()
    if _default_tab not in ('moves', 'comments'):
        _default_tab = 'comments'

    viewer_config = {
        'board_size_desktop': config_loader.get('viewer.board_size_desktop', 500),
        'board_size_mobile':  config_loader.get('viewer.board_size_mobile', 320),
        'play_interval_ms':   config_loader.get('viewer.play_interval_ms', 800),
        'default_tab':        _default_tab,
        'show_coords':        bool(config_loader.get('viewer.show_coords', True)),
    }

    return render_template(
        'player_openings.html',
        username=username,
        games=games,
        total=total,
        favorite_ids=favorite_ids,
        page=page,
        pages=pages,
        per_page=per_page,
        page_links=page_links,
        per_page_links=per_page_links,
        prev_url=prev_url,
        next_url=next_url,
        base_query=base_query,
        active_filters=active_filters,
        date_error=date_error,
        speed_labels=SPEED_LABELS,
        speed_categories=speed_categories,
        popular_openings=popular_openings,
        running_ids=running_ids or [],
        viewer_config=viewer_config,
        current_section='openings',
        filters={
            'opening': opening,
            'results': results or [],
            'color': color or '',
            'opponent': opponent or '',
            'speed': speed or '',
            'date_from': date_from_raw,
            'date_to': date_to_raw,
            'per_page': per_page,
            'page': page,
        }
    )


@main_bp.route('/player/<username>/opponents')
def player_opponents(username):
    """Автодополнение соперников для фильтра на странице дебютов."""
    query = request.args.get('q', '').strip()
    try:
        limit = int(request.args.get('limit', 10))
    except (TypeError, ValueError):
        limit = 10
    limit = max(1, min(limit, 20))

    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    table_name = get_safe_table_name(username)
    original_table = db.table_name
    db.table_name = table_name
    items = []

    try:
        if db.table_exists():
            with db.connection.get_connection() as conn:
                with conn.cursor() as cur:
                    if query:
                        cur.execute(
                            f"""
                            SELECT opponent_name, COUNT(*)
                            FROM "{table_name}"
                            WHERE opponent_name ILIKE %s
                            GROUP BY opponent_name
                            ORDER BY COUNT(*) DESC, opponent_name
                            LIMIT %s;
                            """,
                            (f'%{query}%', limit),
                        )
                    else:
                        cur.execute(
                            f"""
                            SELECT opponent_name, COUNT(*)
                            FROM "{table_name}"
                            GROUP BY opponent_name
                            ORDER BY COUNT(*) DESC, opponent_name
                            LIMIT %s;
                            """,
                            (limit,),
                        )
                    items = [
                        {'name': row[0], 'games': int(row[1])}
                        for row in cur.fetchall()
                    ]
    except Exception as e:
        db.logger.warning(f'Ошибка автодополнения соперников: {e}')
    finally:
        db.table_name = original_table
        db.close()

    return jsonify({'items': items})

def parse_pgn_to_positions(pgn_moves: str) -> list:
    positions = []
    pgn_clean = clean_pgn(pgn_moves)
    full_pgn = f'[Event "?"]\n\n{pgn_clean} *'
    
    try:
        game = chess.pgn.read_game(StringIO(full_pgn))
    except Exception:
        return []
    if not game:
        return []
    
    board = chess.Board()
    
    positions.append({
        'fen': board.fen(),
        'san': None,
        'move_number': 0,
        'color': None,
        'from': None,
        'to': None,
    })
    
    for move in game.mainline_moves():
        try:
            san = board.san(move)
            color = 'white' if board.turn == chess.WHITE else 'black'
            move_number = board.fullmove_number
            
            # Координаты хода в алгебраической нотации (e2, e4)
            from_sq = chess.square_name(move.from_square)  # 'e2'
            to_sq = chess.square_name(move.to_square)      # 'e4'
            
            board.push(move)
            
            positions.append({
                'fen': board.fen(),
                'san': san,
                'move_number': move_number,
                'color': color,
                'from': from_sq,
                'to': to_sq,
            })
        except Exception:
            break
    
    return positions

@main_bp.route('/player/<username>/game/<game_id>/analyze', methods=['POST'])
def analyze_game_route(username, game_id):
    """
    Запускает анализ партии через DeepSeek.

    Возвращает JSON:
      - {status: "done", analysis: "..."} — если анализ уже есть
      - {status: "started", task_id: "..."} — если задача запущена
      - {status: "busy", message: "..."} — если идёт другой анализ
      - {status: "error", message: "..."} — ошибка
    """
    # 1. Проверяем, есть ли уже анализ
    game = get_game_for_analysis(username, game_id)
    if not game:
        return jsonify({
            'status': 'error',
            'message': f'Партия {game_id} не найдена',
        }), 404

    if game['game_analysis']:
        return jsonify({
            'status': 'done',
            'analysis': game['game_analysis'],
            'meta': _game_meta(game),
        })

    # 2. Проверяем, есть ли running-задача для этой пары
    running = analysis_tasks.get_running_task_for(username, game_id)
    if running:
        return jsonify({
            'status': 'started',
            'task_id': running['task_id'],
        })

    # 3. Проверяем доступность DeepSeek
    if not check_health():
        return jsonify({
            'status': 'error',
            'message': 'DeepSeek API недоступен',
        })

    # 4. Создаём задачу (лимит 1)
    task_id = analysis_tasks.create_task(username, game_id)
    if not task_id:
        return jsonify({
            'status': 'busy',
            'message': 'Дождитесь окончания текущего анализа',
        })

    # 5. Запускаем фоновый поток
    t = threading.Thread(
        target=_run_analysis_task,
        args=(task_id, username, game_id),
        daemon=True,
    )
    t.start()

    return jsonify({
        'status': 'started',
        'task_id': task_id,
    })    

@main_bp.route('/player/<username>/game/<game_id>/analyze/status/<task_id>', methods=['GET'])
def analyze_status_route(username, game_id, task_id):
    """
    Возвращает статус задачи анализа.

    JSON:
      - {status: "running"}
      - {status: "done", analysis: "..."}
      - {status: "error", message: "..."}
    """
    # Проверяем, не протухла ли задача (>10 минут)
    analysis_tasks.cleanup_stale_running_task(task_id)

    task = analysis_tasks.get_task(task_id)
    if not task:
        return jsonify({
            'status': 'error',
            'message': 'Задача не найдена',
        }), 404

    # Проверяем, что задача относится к этому игроку/партии
    if task['username'] != username or task['game_id'] != game_id:
        return jsonify({
            'status': 'error',
            'message': 'Задача относится к другой партии',
        }), 400

    if task['status'] == 'done':
        # Загружаем готовый анализ из БД
        game = get_game_for_analysis(username, game_id)
        analysis = game['game_analysis'] if game else ''
        return jsonify({
            'status': 'done',
            'analysis': analysis,
            'meta': _game_meta(game) if game else {},
        })

    if task['status'] == 'error':
        return jsonify({
            'status': 'error',
            'message': task['error'] or 'Неизвестная ошибка',
        })

    # running
    return jsonify({'status': 'running'})    

@main_bp.route('/player/<username>/game/<game_id>/pgn', methods=['GET'])
def get_game_pgn_route(username, game_id):
    """Возвращает краткую нотацию партии (только ходы) для модалки."""
    game = get_game_for_analysis(username, game_id)
    if not game:
        return jsonify({'error': 'Партия не найдена'}), 404

    # Убираем {...} — только ходы
    pgn_clean = clean_pgn(game['pgn_moves'])
    return jsonify({
        'game_id': game_id,
        'pgn': pgn_clean,
    })    

@main_bp.route('/player/<username>/game/<game_id>/view')
def game_view_route(username, game_id):
    """Страница просмотра партии с доской и навигацией."""
    game = get_game_for_analysis(username, game_id)
    if not game:
        abort(404)

    config_loader = ConfigLoader()
    _default_tab = (config_loader.get('viewer.default_tab', 'comments') or 'comments').lower()
    if _default_tab not in ('moves', 'comments'):
        _default_tab = 'comments'

    viewer_config = {
        'board_size_desktop': config_loader.get('viewer.board_size_desktop', 500),
        'board_size_mobile':  config_loader.get('viewer.board_size_mobile', 320),
        'play_interval_ms':   config_loader.get('viewer.play_interval_ms', 800),
        'default_tab':        _default_tab,
        'show_coords':        bool(config_loader.get('viewer.show_coords', True)),
    }

    return render_template(
        'game_view.html',
        username=username,
        game=game,
        viewer_config=viewer_config,
    )  

@main_bp.route('/player/<username>/game/<game_id>/positions', methods=['GET'])
def game_positions_route(username, game_id):
    """Возвращает JSON с позициями для модалки просмотра."""
    game = get_game_for_analysis(username, game_id)
    if not game:
        return jsonify({'error': 'Партия не найдена'}), 404
    
    positions = parse_pgn_to_positions(game['pgn_moves'])
    
    return jsonify({
        'game_id': game_id,
        'positions': positions,
        'meta': _game_meta(game),
        'analysis': game.get('game_analysis') or '',   # ← новое
    })

@main_bp.route('/player/<username>/debuts')
def player_debuts(username):
    """Страница статистики по дебютам (топ дебютов)."""
    stats = get_player_stats(username)
    if not stats.get('exists'):
        flash(f'Игрок {username} не найден.', 'warning')
        return redirect(f'/lichess-analyzer/player/{username}')

    openings = get_opening_stats(username, limit=50)

    config_loader = ConfigLoader()
    _default_tab = (config_loader.get('viewer.default_tab', 'comments') or 'comments').lower()
    if _default_tab not in ('moves', 'comments'):
        _default_tab = 'comments'

    viewer_config = {
        'board_size_desktop': config_loader.get('viewer.board_size_desktop', 500),
        'board_size_mobile':  config_loader.get('viewer.board_size_mobile', 320),
        'play_interval_ms':   config_loader.get('viewer.play_interval_ms', 800),
        'default_tab':        _default_tab,
        'show_coords':        bool(config_loader.get('viewer.show_coords', True)),
    }

    return render_template(
        'player_debuts.html',
        username=username,
        stats=stats,
        openings=openings,
        viewer_config=viewer_config,
        current_section='debuts',
    )

@main_bp.route('/player/<username>/progression')
def player_progression(username):
    """Страница прогресса рейтинга по категории контроля и периоду."""
    stats = get_player_stats(username)
    if not stats.get('exists'):
        flash(f'Игрок {username} не найден.', 'warning')
        return redirect(f'/lichess-analyzer/player/{username}')

    config_loader = ConfigLoader()
    categories, last_speed = get_speed_categories(username)
    valid_speeds = {item['key'] for item in categories}

    # Приоритет: URL -> cookie последнего выбора -> контроль последней игры.
    tc = request.args.get('tc', '').strip()
    if tc not in valid_speeds:
        tc = request.cookies.get('la_tc')
    if tc not in valid_speeds:
        tc = last_speed if last_speed in valid_speeds else None
    if tc is None and categories:
        tc = categories[0]['key']

    period = request.args.get('period', '').strip()
    period_options = [
        ('1d', '1 день'),
        ('1w', '1 неделя'),
        ('1m', '1 месяц'),
        ('3m', '3 месяца'),
        ('6m', '6 месяцев'),
        ('all', 'Всё время'),
    ]
    valid_periods = {key for key, _ in period_options}
    if period not in valid_periods:
        period = config_loader.get('statistics.progression_default_period', '3m')
        if period not in valid_periods:
            period = '3m'

    period_days = {'1d': 0, '1w': 7, '1m': 30, '3m': 90, '6m': 180}
    date_from = None
    if period in period_days:
        date_from = date.today() - timedelta(days=period_days[period])

    rating_progression = get_rating_progression(
        username,
        speed=tc,
        date_from=date_from,
    )
    table_games = rating_progression[:50]
    period_games = len(rating_progression)
    period_wins = sum(1 for g in rating_progression if g.get('result') == 'Win')
    period_win_rate = round(period_wins * 100 / period_games, 1) if period_games else 0
    period_label = dict(period_options).get(period, period)

    # Количество игр по дням: выбранный контроль и все контроли.
    all_progression = (
        get_rating_progression(username, speed=None, date_from=date_from)
        if tc else rating_progression
    )
    period_games_all = len(all_progression)

    daily_games_json = []
    daily_games_all_json = []
    daily_counts = Counter()
    daily_all_counts = Counter()

    for game in rating_progression:
        try:
            game_day = datetime.strptime(game.get('date', ''), '%Y-%m-%d').date()
        except (TypeError, ValueError):
            continue
        daily_counts[game_day] += 1

    for game in all_progression:
        try:
            game_day = datetime.strptime(game.get('date', ''), '%Y-%m-%d').date()
        except (TypeError, ValueError):
            continue
        daily_all_counts[game_day] += 1

    if daily_counts or daily_all_counts:
        known_days = list(daily_counts) + list(daily_all_counts)
        day_start = date_from or min(known_days)
        day_end = date.today()
        if day_start > day_end:
            day_start = day_end
        current_day = day_start
        while current_day <= day_end:
            day_key = current_day.isoformat()
            daily_games_json.append({
                'date': day_key,
                'count': daily_counts.get(current_day, 0),
            })
            daily_games_all_json.append({
                'date': day_key,
                'count': daily_all_counts.get(current_day, 0),
            })
            current_day += timedelta(days=1)
    tc_label = SPEED_LABELS.get(tc, 'Все контроли') if tc else 'Все контроли'

    rating_stats = get_rating_stats(username)

    # Преобразуем данные для графика
    rating_progression_json = []
    for game in rating_progression:
        json_game = {
            'date': game.get('date', '2000-01-01'),
            'my_rating': int(game.get('my_rating', 0) or 0),
            'opponent_rating': int(game.get('opponent_rating', 0) or 0),
            'result': game.get('result', '—'),
            'opening': game.get('opening', '—'),
            'color': game.get('color', '—'),
            'time_control': game.get('time_control', '—'),
            'game_id': game.get('game_id', ''),
            'url': (
                f'/lichess-analyzer/player/{username}/game/'
                f"{game.get('game_id', '')}/view"
                if game.get('game_id') else ''
            ),
        }
        rating_progression_json.append(json_game)

    _default_tab = (config_loader.get('viewer.default_tab', 'comments') or 'comments').lower()
    if _default_tab not in ('moves', 'comments'):
        _default_tab = 'comments'

    viewer_config = {
        'board_size_desktop': config_loader.get('viewer.board_size_desktop', 500),
        'board_size_mobile':  config_loader.get('viewer.board_size_mobile', 320),
        'play_interval_ms':   config_loader.get('viewer.play_interval_ms', 800),
        'default_tab':        _default_tab,
        'show_coords':        bool(config_loader.get('viewer.show_coords', True)),
    }

    response = make_response(render_template(
        'player_progression.html',
        username=username,
        stats=stats,
        rating_stats=rating_stats,
        rating_progression=rating_progression,
        table_games=table_games,
        period_games=period_games,
        period_wins=period_wins,
        period_win_rate=period_win_rate,
        period_games_all=period_games_all,
        daily_games_json=daily_games_json,
        daily_games_all_json=daily_games_all_json,
        rating_progression_json=rating_progression_json,
        speed_categories=categories,
        current_tc=tc,
        tc_label=tc_label,
        period=period,
        period_label=period_label,
        period_options=period_options,
        viewer_config=viewer_config,
        current_section='progression',
    ))

    # Запоминаем выбранный контроль для следующего визита.
    if request.args.get('tc') in valid_speeds:
        response.set_cookie(
            'la_tc',
            tc,
            max_age=31536000,
            path='/',
            samesite='Lax',
        )

    return response


@main_bp.route('/player/<username>/time-control')
def player_time_control(username):
    """Страница статистики по контролю времени."""
    stats = get_player_stats(username)
    if not stats.get('exists'):
        flash(f'Игрок {username} не найден.', 'warning')
        return redirect(f'/lichess-analyzer/player/{username}')

    time_stats = get_time_control_stats(username)

    config_loader = ConfigLoader()
    _default_tab = (config_loader.get('viewer.default_tab', 'comments') or 'comments').lower()
    if _default_tab not in ('moves', 'comments'):
        _default_tab = 'comments'

    viewer_config = {
        'board_size_desktop': config_loader.get('viewer.board_size_desktop', 500),
        'board_size_mobile':  config_loader.get('viewer.board_size_mobile', 320),
        'play_interval_ms':   config_loader.get('viewer.play_interval_ms', 800),
        'default_tab':        _default_tab,
        'show_coords':        bool(config_loader.get('viewer.show_coords', True)),
    }

    return render_template(
        'player_time_control.html',
        username=username,
        stats=stats,
        time_stats=time_stats,
        viewer_config=viewer_config,
        current_section='time-control',
    )    

@main_bp.route('/player/<username>/move-length')
def player_move_length(username):
    """Страница статистики по длине партий + топ коротких/длинных."""
    stats = get_player_stats(username)
    if not stats.get('exists'):
        flash(f'Игрок {username} не найден.', 'warning')
        return redirect(f'/lichess-analyzer/player/{username}')

    move_stats = get_move_stats(username)
    move_game_ids = [
        g['game_id']
        for key in ('shortest', 'longest')
        for g in move_stats.get(key, [])
    ]
    favorite_ids = get_favorite_ids(username, move_game_ids)

    config_loader = ConfigLoader()
    _default_tab = (config_loader.get('viewer.default_tab', 'comments') or 'comments').lower()
    if _default_tab not in ('moves', 'comments'):
        _default_tab = 'comments'

    viewer_config = {
        'board_size_desktop': config_loader.get('viewer.board_size_desktop', 500),
        'board_size_mobile':  config_loader.get('viewer.board_size_mobile', 320),
        'play_interval_ms':   config_loader.get('viewer.play_interval_ms', 800),
        'default_tab':        _default_tab,
        'show_coords':        bool(config_loader.get('viewer.show_coords', True)),
    }

    return render_template(
        'player_move_length.html',
        username=username,
        stats=stats,
        move_stats=move_stats,
        favorite_ids=favorite_ids,
        viewer_config=viewer_config,
        current_section='move-length',
    )    