#!/usr/bin/env python3
"""
Детальный анализ игр игрока: самые длинные и короткие партии
"""
import sys
import argparse
from pathlib import Path
from tabulate import tabulate
from datetime import datetime

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager


class DetailedGameAnalyzer:
    """Детальный анализ игр игрока"""
    
    def __init__(self, username: str):
        self.username = username
        self.table_name = f"games_{username.lower()}"
        self.config = ConfigLoader()
        self.db = DatabaseManager(self.config, 'local')
        self.db.table_name = self.table_name
        self.total_games = 0
        
    def close(self):
        """Закрывает подключение"""
        self.db.close()
    
    def table_exists(self) -> bool:
        """Проверяет существование таблицы"""
        return self.db.table_exists()
    
    def get_longest_games(self, limit: int = 10) -> list:
        """Получает самые длинные партии"""
        with self.db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT 
                        game_id,
                        game_date,
                        player_color,
                        opponent_name,
                        result,
                        move_count,
                        my_rating,
                        opponent_rating,
                        opening_name,
                        accuracy
                    FROM {self.table_name}
                    WHERE move_count > 0
                    ORDER BY move_count DESC
                    LIMIT %s;
                """, (limit,))
                
                return [{
                    'game_id': row[0],
                    'date': row[1],
                    'color': row[2],
                    'opponent': row[3],
                    'result': row[4],
                    'move_count': row[5],
                    'my_rating': row[6],
                    'opponent_rating': row[7],
                    'opening': row[8] if row[8] else '—',
                    'accuracy': row[9] if row[9] else 0
                } for row in cur.fetchall()]
    
    def get_shortest_games(self, limit: int = 10) -> list:
        """Получает самые короткие партии"""
        with self.db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT 
                        game_id,
                        game_date,
                        player_color,
                        opponent_name,
                        result,
                        move_count,
                        my_rating,
                        opponent_rating,
                        opening_name,
                        accuracy
                    FROM {self.table_name}
                    WHERE move_count > 0
                    ORDER BY move_count ASC
                    LIMIT %s;
                """, (limit,))
                
                return [{
                    'game_id': row[0],
                    'date': row[1],
                    'color': row[2],
                    'opponent': row[3],
                    'result': row[4],
                    'move_count': row[5],
                    'my_rating': row[6],
                    'opponent_rating': row[7],
                    'opening': row[8] if row[8] else '—',
                    'accuracy': row[9] if row[9] else 0
                } for row in cur.fetchall()]
    
    def get_game_by_id(self, game_id: str) -> dict:
        """Получает информацию об игре по ID"""
        with self.db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT 
                        game_id,
                        game_date,
                        player_color,
                        opponent_name,
                        result,
                        move_count,
                        my_rating,
                        opponent_rating,
                        opening_name,
                        accuracy,
                        pgn_moves
                    FROM {self.table_name}
                    WHERE game_id = %s;
                """, (game_id,))
                
                row = cur.fetchone()
                if row:
                    return {
                        'game_id': row[0],
                        'date': row[1],
                        'color': row[2],
                        'opponent': row[3],
                        'result': row[4],
                        'move_count': row[5],
                        'my_rating': row[6],
                        'opponent_rating': row[7],
                        'opening': row[8] if row[8] else '—',
                        'accuracy': row[9] if row[9] else 0,
                        'pgn': row[10] if row[10] else 'Нет нотации'
                    }
                return None
    
    def get_move_stats(self) -> dict:
        """Получает статистику по длине партий"""
        with self.db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT 
                        COUNT(*) as total,
                        MIN(move_count) as min_moves,
                        MAX(move_count) as max_moves,
                        ROUND(AVG(move_count), 1) as avg_moves,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY move_count) as median_moves,
                        ROUND(AVG(accuracy), 1) as avg_accuracy
                    FROM {self.table_name}
                    WHERE move_count > 0;
                """)
                row = cur.fetchone()
                return {
                    'total': row[0],
                    'min_moves': row[1],
                    'max_moves': row[2],
                    'avg_moves': row[3],
                    'median_moves': row[4],
                    'avg_accuracy': row[5]
                }
    
    def print_report(self):
        """Печатает детальный отчет"""
        print("\n" + "=" * 80)
        print(f"📊 ДЕТАЛЬНЫЙ АНАЛИЗ ИГР ИГРОКА: {self.username}")
        print("=" * 80)
        
        # Проверяем существование таблицы
        if not self.table_exists():
            print(f"❌ Игрок '{self.username}' не найден в БД!")
            return
        
        # Статистика по длине
        stats = self.get_move_stats()
        print(f"\n📏 СТАТИСТИКА ПО ДЛИНЕ ПАРТИЙ:")
        print(f"  Всего игр: {stats['total']}")
        print(f"  Минимальная длина: {stats['min_moves']} ходов")
        print(f"  Максимальная длина: {stats['max_moves']} ходов")
        print(f"  Средняя длина: {stats['avg_moves']} ходов")
        print(f"  Медианная длина: {stats['median_moves']} ходов")
        if stats['avg_accuracy']:
            print(f"  Средняя точность: {stats['avg_accuracy']:.1f}%")
        
        # Самые длинные партии
        print("\n" + "=" * 80)
        print(f"🏆 ТОП-10 САМЫХ ДЛИННЫХ ПАРТИЙ:")
        print("=" * 80)
        
        longest = self.get_longest_games(10)
        print("\n  # | Дата       | Цвет | Соперник            | Ходов | Результат | Точность | Дебют")
        print("  " + "-" * 100)
        
        for i, game in enumerate(longest, 1):
            color_emoji = "⚪" if game['color'] == 'white' else "⚫"
            result_emoji = "✅" if game['result'] == 'Win' else "❌" if game['result'] == 'Loss' else "➖"
            acc_str = f"{game['accuracy']:.1f}%" if game['accuracy'] else "N/A"
            date_str = game['date'].strftime('%Y-%m-%d')
            print(f"  {i:2d} | {date_str} | {color_emoji}   | {game['opponent'][:20]:20s} | {game['move_count']:5d} | {game['result']:6s} {result_emoji} | {acc_str:6s} | {game['opening'][:25]}")
        
        # Самая длинная партия с аннотацией
        if longest:
            print("\n" + "=" * 80)
            print("📖 АННОТАЦИЯ САМОЙ ДЛИННОЙ ПАРТИИ:")
            print("=" * 80)
            
            longest_game = longest[0]
            print(f"\n  🏆 Рекорд: {longest_game['move_count']} ходов")
            print(f"  📅 Дата: {longest_game['date'].strftime('%d.%m.%Y')}")
            print(f"  🎯 Игрок: {self.username} ({longest_game['color']})")
            print(f"  👤 Соперник: {longest_game['opponent']}")
            print(f"  📊 Результат: {longest_game['result']}")
            print(f"  📈 Рейтинг: {longest_game['my_rating']} vs {longest_game['opponent_rating']}")
            print(f"  📖 Дебют: {longest_game['opening']}")
            if longest_game['accuracy']:
                print(f"  🎯 Точность: {longest_game['accuracy']:.1f}%")
            print(f"  🆔 ID игры: {longest_game['game_id']}")
        
        # Самые короткие партии
        print("\n" + "=" * 80)
        print(f"⚡ ТОП-10 САМЫХ КОРОТКИХ ПАРТИЙ:")
        print("=" * 80)
        
        shortest = self.get_shortest_games(10)
        print("\n  # | Дата       | Цвет | Соперник            | Ходов | Результат | Точность | Дебют")
        print("  " + "-" * 100)
        
        for i, game in enumerate(shortest, 1):
            color_emoji = "⚪" if game['color'] == 'white' else "⚫"
            result_emoji = "✅" if game['result'] == 'Win' else "❌" if game['result'] == 'Loss' else "➖"
            acc_str = f"{game['accuracy']:.1f}%" if game['accuracy'] else "N/A"
            date_str = game['date'].strftime('%Y-%m-%d')
            print(f"  {i:2d} | {date_str} | {color_emoji}   | {game['opponent'][:20]:20s} | {game['move_count']:5d} | {game['result']:6s} {result_emoji} | {acc_str:6s} | {game['opening'][:25]}")
        
        # Самая короткая партия с аннотацией
        if shortest:
            print("\n" + "=" * 80)
            print("⚡ АННОТАЦИЯ САМОЙ КОРОТКОЙ ПАРТИИ:")
            print("=" * 80)
            
            shortest_game = shortest[0]
            print(f"\n  ⚡ Рекорд: {shortest_game['move_count']} ходов")
            print(f"  📅 Дата: {shortest_game['date'].strftime('%d.%m.%Y')}")
            print(f"  🎯 Игрок: {self.username} ({shortest_game['color']})")
            print(f"  👤 Соперник: {shortest_game['opponent']}")
            print(f"  📊 Результат: {shortest_game['result']}")
            print(f"  📈 Рейтинг: {shortest_game['my_rating']} vs {shortest_game['opponent_rating']}")
            print(f"  📖 Дебют: {shortest_game['opening']}")
            if shortest_game['accuracy']:
                print(f"  🎯 Точность: {shortest_game['accuracy']:.1f}%")
            print(f"  🆔 ID игры: {shortest_game['game_id']}")
        
        # Показать полную нотацию самой длинной партии (по запросу)
        if longest:
            print("\n" + "=" * 80)
            print("📝 ПЕРВЫЕ 10 ХОДОВ САМОЙ ДЛИННОЙ ПАРТИИ:")
            print("=" * 80)
            
            # Получаем полную игру
            game_detail = self.get_game_by_id(longest_game['game_id'])
            if game_detail and game_detail['pgn'] != 'Нет нотации':
                pgn = game_detail['pgn']
                # Показываем первые 10 ходов
                moves = pgn.split()
                if len(moves) > 20:
                    first_moves = ' '.join(moves[:20])
                    print(f"\n  {first_moves} ...")
                    print(f"\n  ... и еще {len(moves) - 20} ходов")
                else:
                    print(f"\n  {pgn}")
            else:
                print("\n  Нотация не доступна")
        
        print("\n" + "=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description='Детальный анализ игр игрока: самые длинные и короткие партии',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python scripts/06_analyze_games_detailed.py --username DenNedelin
  python scripts/06_analyze_games_detailed.py --username faarxa5a
        """
    )
    
    parser.add_argument('--username', '-u', type=str, required=True,
                       help='Имя пользователя для анализа')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Подробный вывод')
    
    args = parser.parse_args()
    
    try:
        analyzer = DetailedGameAnalyzer(args.username)
        
        if not analyzer.table_exists():
            print(f"❌ Игрок '{args.username}' не найден в БД!")
            print("\nСначала скачайте его игры:")
            print(f"  python scripts/04_download_player_games.py --username '{args.username}'")
            sys.exit(1)
        
        analyzer.print_report()
        analyzer.close()
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Прервано пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()