"""
Анализ партии Stockfish и хранение оценок по полуходам.
"""
from __future__ import annotations

import io
import logging
import shutil
from pathlib import Path
from typing import Callable, Optional

import chess
import chess.engine
import chess.pgn

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager
from core.utils.lichess import player_table_name

logger = logging.getLogger(__name__)


def get_engine_config(config: Optional[ConfigLoader] = None) -> dict:
    config = config or ConfigLoader()
    try:
        depth = int(config.get('engine.depth', 14))
    except (TypeError, ValueError):
        depth = 14
    try:
        hash_mb = int(config.get('engine.hash_mb', 16))
    except (TypeError, ValueError):
        hash_mb = 16
    try:
        threads = int(config.get('engine.threads', 1))
    except (TypeError, ValueError):
        threads = 1
    return {
        'enabled': bool(config.get('engine.enabled', True)),
        'path': str(config.get('engine.path', '/usr/games/stockfish')),
        'depth': max(1, min(depth, 30)),
        'hash_mb': max(1, min(hash_mb, 64)),
        'threads': max(1, min(threads, 2)),
    }


def find_stockfish(path: str) -> str:
    candidate = path or '/usr/games/stockfish'
    found = shutil.which(candidate) if not Path(candidate).is_absolute() else candidate
    if not found or not Path(found).is_file():
        raise RuntimeError(f'Stockfish не найден: {candidate}')
    return found


def get_game_pgn(username: str, game_id: str, config: Optional[ConfigLoader] = None) -> Optional[str]:
    config = config or ConfigLoader()
    db = DatabaseManager(config, 'local')
    table = player_table_name(username)
    original = db.table_name
    db.table_name = table
    try:
        if not db.table_exists():
            return None
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'SELECT pgn_moves FROM "{table}" WHERE game_id = %s LIMIT 1;',
                    (game_id,),
                )
                row = cur.fetchone()
                return row[0] if row else None
    finally:
        db.table_name = original
        db.close()


def get_engine_evals(username: str, game_id: str,
                     config: Optional[ConfigLoader] = None) -> dict:
    config = config or ConfigLoader()
    db = DatabaseManager(config, 'local')
    result = {}
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ply, eval_cp, mate, depth
                    FROM game_engine_evals
                    WHERE player_username = %s AND game_id = %s;
                    """,
                    (username.lower(), game_id),
                )
                for ply, eval_cp, mate, depth in cur.fetchall():
                    result[int(ply)] = {
                        'eval_cp': eval_cp,
                        'mate': mate,
                        'depth': depth,
                    }
    except Exception as e:
        logger.warning('Не удалось прочитать engine evals: %s', e)
    finally:
        db.close()
    return result


def _score_to_white(score):
    if score is None:
        return None, None
    white = score.white()
    if white.is_mate():
        return None, white.mate()
    return white.score(), None


def run_engine_analysis(
    username: str,
    game_id: str,
    depth: int,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    config: Optional[ConfigLoader] = None,
) -> int:
    """Считает оценки по всем полуходам и сохраняет их в game_engine_evals."""
    config = config or ConfigLoader()
    cfg = get_engine_config(config)
    pgn_text = get_game_pgn(username, game_id, config)
    if not pgn_text:
        raise RuntimeError('Партия не найдена')

    pgn_game = chess.pgn.read_game(io.StringIO(pgn_text))
    if not pgn_game:
        raise RuntimeError('Не удалось разобрать PGN')

    nodes = [node for node in pgn_game.mainline()]
    total = len(nodes)
    if progress_cb:
        progress_cb(0, total)

    binary = find_stockfish(cfg['path'])
    engine = chess.engine.SimpleEngine.popen_uci(binary)
    engine.configure({'Hash': cfg['hash_mb'], 'Threads': cfg['threads']})
    engine_name = str((engine.id or {}).get('name') or 'Stockfish')[:50]

    db = DatabaseManager(config, 'local')
    try:
        for index, node in enumerate(nodes, start=1):
            board = node.board()
            info = engine.analyse(board, chess.engine.Limit(depth=depth))
            eval_cp, mate = _score_to_white(info.get('score'))
            san = node.san() if node.move else None

            with db.connection.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO game_engine_evals
                            (player_username, game_id, ply, san, eval_cp, mate,
                             depth, engine)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (player_username, game_id, ply)
                        DO UPDATE SET
                            san = EXCLUDED.san,
                            eval_cp = EXCLUDED.eval_cp,
                            mate = EXCLUDED.mate,
                            depth = EXCLUDED.depth,
                            engine = EXCLUDED.engine,
                            created_at = NOW();
                        """,
                        (username.lower(), game_id, node.ply(), san,
                         eval_cp, mate, depth, engine_name),
                    )
                conn.commit()

            if progress_cb:
                progress_cb(index, total)
        return total
    finally:
        try:
            engine.quit()
        except Exception:
            pass
        db.close()


def _lock_key(username: str, game_id: str) -> int:
    import zlib
    return zlib.crc32(f'{username.lower()}:{game_id}'.encode('utf-8')) & 0x7fffffff


def ensure_engine_evals(
    username: str,
    game_id: str,
    depth: int,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    config: Optional[ConfigLoader] = None,
) -> int:
    """Считает evals, если их ещё нет; защищено advisory-lock по партии."""
    config = config or ConfigLoader()
    existing = get_engine_evals(username, game_id, config)
    if existing:
        return 0

    db = DatabaseManager(config, 'local')
    lock_key = _lock_key(username, game_id)
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT pg_advisory_lock(%s);', (lock_key,))
                try:
                    if get_engine_evals(username, game_id, config):
                        return 0
                    return run_engine_analysis(
                        username, game_id, depth,
                        progress_cb=progress_cb,
                        config=config,
                    )
                finally:
                    cur.execute('SELECT pg_advisory_unlock(%s);', (lock_key,))
                    conn.commit()
    finally:
        db.close()


def build_eval_block(
    username: str,
    game_id: str,
    config: Optional[ConfigLoader] = None,
) -> str:
    """Текст с оценками ходов для промпта DeepSeek."""
    config = config or ConfigLoader()
    pgn_text = get_game_pgn(username, game_id, config)
    if not pgn_text:
        return ''
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if not game:
        return ''
    engine_evals = get_engine_evals(username, game_id, config)
    lines = []
    for node in game.mainline():
        if not node.move:
            continue
        eval_cp = None
        mate = None
        score = node.eval()
        if score is not None:
            white = score.white()
            if white.is_mate():
                mate = white.mate()
            else:
                eval_cp = white.score()
        item = engine_evals.get(node.ply())
        if item:
            eval_cp = item.get('eval_cp')
            mate = item.get('mate')
        if eval_cp is None and mate is None:
            continue
        if mate is not None:
            value = f'#{mate:+d}'
        else:
            value = f'{eval_cp / 100:+.2f}'
        number = node.parent.board().fullmove_number if node.parent else 1
        color = '...' if node.parent and node.parent.board().turn == chess.BLACK else '.'
        lines.append(f'{number}{color} {node.san()} {value}')
    if not lines:
        return ''
    return (
        'Оценки позиций (Stockfish/Lichess, + = перевес белых):\n'
        + '\n'.join(lines)
    )
