#!/usr/bin/env python3
"""
Получение PGN-нотации конкретной партии из БД.
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager


def get_safe_table_name(username: str) -> str:
    safe = username.replace('-', '_').replace('.', '_')
    return f"games_{safe.lower()}"


def get_game_pgn(username: str, game_id: str) -> dict:
    """Возвращает данные партии, включая pgn_moves."""
    print(f"DEBUG: username={username}, game_id={game_id}")
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')

    table_name = get_safe_table_name(username)
    original_table = db.table_name
    db.table_name = table_name
    print(f"DEBUG: table_name={table_name}")

    if not db.table_exists():
        db.table_name = original_table
        db.close()
        return None

    try:
        with db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT
                        game_id,
                        game_date,
                        player_color,
                        opponent_name,
                        result,
                        opening_name,
                        move_count,
                        pgn_moves,
                        game_url
                    FROM {table_name}
                    WHERE game_id = %s;
                """, (game_id,))

                row = cur.fetchone()
                if not row:
                    return None

                return {
                    'game_id': row[0],
                    'date': row[1],
                    'color': row[2],
                    'opponent': row[3],
                    'result': row[4],
                    'opening': row[5],
                    'move_count': row[6],
                    'pgn_moves': row[7] or '',
                    'game_url': row[8] or f"https://lichess.org/{row[0]}",
                }
    finally:
        db.table_name = original_table
        db.close()


def clean_pgn(pgn: str) -> str:
    """Убирает комментарии вида { ... } из PGN"""
    import re
    return re.sub(r'\s*\{[^}]*\}\s*', ' ', pgn).strip()


def main():
    parser = argparse.ArgumentParser(
        description='Получение PGN-нотации партии из БД',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python scripts/07_get_game_pgn.py --username DenNedelin --game-id 0b43Lfb6
  python scripts/07_get_game_pgn.py -u DenNedelin -g 0b43Lfb6 --raw
  python scripts/07_get_game_pgn.py -u DenNedelin -g 0b43Lfb6 --clean
        """
    )
    parser.add_argument('--username', '-u', required=True, help='Имя игрока')
    parser.add_argument('--game-id', '-g', required=True, help='ID партии на Lichess')
    parser.add_argument('--raw', action='store_true',
                        help='Вывести только PGN-нотацию')
    parser.add_argument('--clean', action='store_true',
                        help='Убрать комментарии { ... } (оценки, часы)')
    parser.add_argument('--verbose', '-v', action='store_true')

    args = parser.parse_args()

    game = get_game_pgn(args.username, args.game_id)

    if not game:
        print(f"❌ Партия '{args.game_id}' для игрока '{args.username}' не найдена")
        sys.exit(1)

    pgn = game['pgn_moves']
    if args.clean:
        pgn = clean_pgn(pgn)

    if args.raw:
        print(pgn)
        return

    print(f"\n♟️  Партия: {game['game_id']}")
    print(f"📅 Дата: {game['date']}")
    print(f"🎨 Цвет: {game['color']}")
    print(f"👤 Соперник: {game['opponent']}")
    print(f"🏆 Результат: {game['result']}")
    print(f"📖 Дебют: {game['opening']}")
    print(f"🔢 Ходов: {game['move_count']}")
    print(f"🔗 Ссылка: {game['game_url']}")
    print("\n" + "=" * 70)
    print("PGN:")
    print("=" * 70)
    print(pgn if pgn else "(нотация не сохранена)")
    print("=" * 70)


if __name__ == '__main__':
    main()
