#!/usr/bin/env python3
"""
Тест Stockfish на 1–2 партиях из базы.

Запуск из корня проекта:
  venv/bin/python scripts/engine/test_stockfish.py --player DenNedelin --limit 2 --depth 10
"""
from __future__ import annotations

import argparse
import io
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import chess
import chess.engine
import chess.pgn

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager
from core.utils.lichess import player_table_name


def find_stockfish(explicit: str | None) -> str:
    candidates = [explicit, "/usr/games/stockfish", "stockfish"]
    for candidate in candidates:
        if not candidate:
            continue
        path = shutil.which(candidate) if not Path(candidate).is_absolute() else candidate
        if path and Path(path).is_file():
            return path
    raise SystemExit("Stockfish не найден. Сначала запустите scripts/engine/install_stockfish.sh")


def score_to_cp(score):
    """PovScore/Score в сантипешки; None для мата."""
    if score is None:
        return None
    white = score.white()
    if white.is_mate():
        return None
    return white.score()


def score_text(score):
    if score is None:
        return "—"
    white = score.white()
    if white.is_mate():
        return f"#{white.mate():+d}"
    cp = white.score()
    return f"{cp / 100:+.2f}" if cp is not None else "—"


def load_games(player: str, limit: int, config: ConfigLoader):
    db = DatabaseManager(config, 'local')
    table = player_table_name(player)
    original = db.table_name
    db.table_name = table
    if not db.table_exists():
        db.table_name = original
        db.close()
        raise SystemExit(f"Таблица {table} не найдена")
    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'''
                    SELECT game_id, opponent_name, game_date, move_count, pgn_moves
                    FROM "{table}"
                    WHERE pgn_moves LIKE %s
                    ORDER BY game_date DESC
                    LIMIT %s;
                    ''',
                    ('%[%eval%', limit),
                )
                return cur.fetchall()
    finally:
        db.table_name = original
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--player', default='DenNedelin')
    parser.add_argument('--limit', type=int, default=2)
    parser.add_argument('--depth', type=int, default=10)
    parser.add_argument('--step', type=int, default=4,
                        help='проверять каждый N-й полуход (1 = все)')
    parser.add_argument('--hash', type=int, default=16)
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--stockfish', default=None)
    parser.add_argument('--max-positions', type=int, default=40)
    args = parser.parse_args()

    args.limit = max(1, min(args.limit, 5))
    args.depth = max(1, args.depth)
    args.step = max(1, args.step)

    binary = find_stockfish(args.stockfish)
    config = ConfigLoader()
    games = load_games(args.player, args.limit, config)
    if not games:
        print('Нет партий с [%eval]')
        return 1

    print(f'Stockfish: {binary}')
    print(f'Партий: {len(games)}, depth={args.depth}, step={args.step}, Hash={args.hash}')
    total_positions = 0
    total_seconds = 0.0
    started = time.monotonic()

    engine = chess.engine.SimpleEngine.popen_uci(binary)
    engine.configure({'Hash': args.hash, 'Threads': args.threads})
    try:
        for game_no, (game_id, opponent, game_date, move_count, pgn_text) in enumerate(games, 1):
            pgn_game = chess.pgn.read_game(io.StringIO(pgn_text))
            if not pgn_game:
                print(f'\n[{game_no}] {game_id}: PGN не разобран')
                continue

            print(f'\n[{game_no}] {game_id} · {opponent or "?"} · {game_date} · {move_count or "?"} ply')
            node = pgn_game
            sampled = 0
            game_started = time.monotonic()

            while True:
                node = node.next()
                if node is None:
                    break
                # node.board() — позиция после хода; node.eval() — Lichess eval для неё.
                if node.ply() % args.step != 0:
                    continue
                if total_positions >= args.max_positions:
                    break

                lichess_score = node.eval()
                if lichess_score is None:
                    continue

                board = node.board()
                info = engine.analyse(board, chess.engine.Limit(depth=args.depth))
                sf_score = info.get('score')
                elapsed = info.get('time', 0) or 0
                total_seconds += elapsed
                total_positions += 1
                sampled += 1

                lichess_cp = score_to_cp(lichess_score)
                sf_cp = score_to_cp(sf_score)
                diff = ''
                if lichess_cp is not None and sf_cp is not None:
                    diff = f' Δ {(sf_cp - lichess_cp) / 100:+.2f}'

                print(
                    f'  ply {node.ply():>3} {node.san():<6} '
                    f'SF {score_text(sf_score):>6}  '
                    f'Lichess {score_text(lichess_score):>6}'
                    f'{diff}  {elapsed:.2f}s'
                )
            game_elapsed = time.monotonic() - game_started
            print(f'  проверено позиций: {sampled}, время: {game_elapsed:.2f}s')
    finally:
        engine.quit()

    elapsed = time.monotonic() - started
    print('\n== Итог ==')
    print(f'Позиций: {total_positions}')
    print(f'Время: {elapsed:.2f}s')
    if total_positions:
        print(f'Среднее на позицию: {elapsed / total_positions:.3f}s')
    print(f'Пиковая RSS (Python): {__import__("resource").getrusage(__import__("resource").RUSAGE_SELF).ru_maxrss} KB')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
