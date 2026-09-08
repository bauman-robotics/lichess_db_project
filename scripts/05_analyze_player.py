#!/usr/bin/env python3
"""
Анализ игр другого игрока из отдельной таблицы
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


class PlayerAnalyzer:
    """Анализ игр конкретного игрока"""
    
    def __init__(self, username: str):
        self.username = username
        self.table_name = f"games_{username.lower()}"
        self.config = ConfigLoader()
        self.db = DatabaseManager(self.config, 'local')
        self.db.table_name = self.table_name  # Подменяем таблицу
        self.total_games = 0
        
    def close(self):
        """Закрывает подключение"""
        self.db.close()
    
    def table_exists(self) -> bool:
        """Проверяет существование таблицы"""
        return self.db.table_exists()
    
    def get_basic_stats(self) -> dict:
        """Получает базовую статистику"""
        stats = self.db.get_table_stats()
        self.total_games = stats.get('total_records', 0)
        
        result_dist = {}
        for result, count in stats.get('results_distribution', []):
            result_dist[result] = count
        
        return {
            'total': self.total_games,
            'first_game': stats.get('first_game'),
            'last_game': stats.get('last_game'),
            'unique_opponents': stats.get('unique_opponents', 0),
            'avg_accuracy': stats.get('avg_accuracy', 0),
            'results': result_dist,
            'wins': result_dist.get('Win', 0),
            'losses': result_dist.get('Loss', 0),
            'draws': result_dist.get('Draw', 0)
        }
    
    def get_stats_by_color(self) -> list:
        """Статистика по цвету"""
        with self.db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT 
                        player_color,
                        COUNT(*) as games,
                        SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN result = 'Loss' THEN 1 ELSE 0 END) as losses,
                        SUM(CASE WHEN result = 'Draw' THEN 1 ELSE 0 END) as draws,
                        ROUND(AVG(accuracy), 1) as avg_accuracy
                    FROM {self.table_name}
                    GROUP BY player_color;
                """)
                
                return [{
                    'color': row[0],
                    'games': row[1],
                    'wins': row[2],
                    'losses': row[3],
                    'draws': row[4],
                    'avg_accuracy': row[5] if row[5] else 0
                } for row in cur.fetchall()]
    
    def get_top_opponents(self, limit: int = 10) -> list:
        """Топ соперников"""
        with self.db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT 
                        opponent_name,
                        COUNT(*) as games,
                        SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN result = 'Loss' THEN 1 ELSE 0 END) as losses,
                        SUM(CASE WHEN result = 'Draw' THEN 1 ELSE 0 END) as draws,
                        ROUND(AVG(accuracy), 1) as avg_accuracy
                    FROM {self.table_name}
                    GROUP BY opponent_name
                    HAVING COUNT(*) >= 3
                    ORDER BY games DESC
                    LIMIT %s;
                """, (limit,))
                
                return [{
                    'name': row[0],
                    'games': row[1],
                    'wins': row[2],
                    'losses': row[3],
                    'draws': row[4],
                    'avg_accuracy': row[5] if row[5] else 0
                } for row in cur.fetchall()]
    
    def get_top_openings(self, limit: int = 10) -> list:
        """Топ дебютов"""
        with self.db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT 
                        opening_name,
                        COUNT(*) as games,
                        SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN result = 'Loss' THEN 1 ELSE 0 END) as losses,
                        SUM(CASE WHEN result = 'Draw' THEN 1 ELSE 0 END) as draws,
                        ROUND(AVG(accuracy), 1) as avg_accuracy
                    FROM {self.table_name}
                    WHERE opening_name IS NOT NULL
                    GROUP BY opening_name
                    HAVING COUNT(*) >= 3
                    ORDER BY games DESC
                    LIMIT %s;
                """, (limit,))
                
                return [{
                    'name': row[0],
                    'games': row[1],
                    'wins': row[2],
                    'losses': row[3],
                    'draws': row[4],
                    'avg_accuracy': row[5] if row[5] else 0
                } for row in cur.fetchall()]
    
    def get_rating_progression(self, limit: int = 30) -> list:
        """Прогресс рейтинга"""
        with self.db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT 
                        game_date,
                        my_rating,
                        opponent_rating,
                        result,
                        accuracy
                    FROM {self.table_name}
                    ORDER BY game_date DESC
                    LIMIT %s;
                """, (limit,))
                
                return [{
                    'date': row[0],
                    'my_rating': row[1],
                    'opponent_rating': row[2],
                    'result': row[3],
                    'accuracy': row[4] if row[4] else 0
                } for row in cur.fetchall()]
    
    def get_monthly_stats(self) -> list:
        """Ежемесячная статистика"""
        with self.db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT 
                        DATE_TRUNC('month', game_date) as month,
                        COUNT(*) as games,
                        SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN result = 'Loss' THEN 1 ELSE 0 END) as losses,
                        SUM(CASE WHEN result = 'Draw' THEN 1 ELSE 0 END) as draws,
                        ROUND(AVG(accuracy), 1) as avg_accuracy,
                        ROUND(AVG(my_rating), 0) as avg_rating
                    FROM {self.table_name}
                    GROUP BY month
                    ORDER BY month DESC;
                """)
                
                return [{
                    'month': row[0],
                    'games': row[1],
                    'wins': row[2],
                    'losses': row[3],
                    'draws': row[4],
                    'avg_accuracy': row[5] if row[5] else 0,
                    'avg_rating': row[6] if row[6] else 0
                } for row in cur.fetchall()]
    
    def print_report(self, detailed: bool = False):
        """Печатает отчет"""
        print("\n" + "=" * 70)
        print(f"📊 ОТЧЕТ ПО ИГРАМ ИГРОКА: {self.username}")
        print("=" * 70)
        
        # Базовая статистика
        stats = self.get_basic_stats()
        print(f"\n📅 Всего игр: {stats['total']}")
        print(f"📅 Период: {stats['first_game']} - {stats['last_game']}")
        print(f"👥 Уникальных соперников: {stats['unique_opponents']}")
        
        if stats['avg_accuracy']:
            print(f"🎯 Средняя точность: {stats['avg_accuracy']:.1f}%")
        else:
            print("🎯 Средняя точность: Нет данных")
        
        print("\n📊 РАСПРЕДЕЛЕНИЕ РЕЗУЛЬТАТОВ:")
        for result, count in stats['results'].items():
            pct = count / stats['total'] * 100 if stats['total'] > 0 else 0
            bar = "█" * int(pct / 2)
            print(f"  {result:6s}: {count:4d} ({pct:5.1f}%) {bar}")
        
        win_rate = stats['wins'] / stats['total'] * 100 if stats['total'] > 0 else 0
        print(f"\n🏆 Процент побед: {win_rate:.1f}%")
        
        # Статистика по цвету
        print("\n🎯 РЕЗУЛЬТАТЫ ПО ЦВЕТУ ФИГУР:")
        print("  Цвет    | Игры | Победы | Поражения | Ничьи | Точность")
        print("  " + "-" * 60)
        
        color_stats = self.get_stats_by_color()
        for cs in color_stats:
            color_name = "Белые" if cs['color'] == 'white' else "Черные"
            win_pct = cs['wins'] / cs['games'] * 100 if cs['games'] > 0 else 0
            acc_str = f"{cs['avg_accuracy']:5.1f}%" if cs['avg_accuracy'] else "  N/A"
            print(f"  {color_name:7s} | {cs['games']:4d} | {cs['wins']:5d} ({win_pct:5.1f}%) | {cs['losses']:7d} | {cs['draws']:5d} | {acc_str}")
        
        # Топ соперников
        print("\n🏆 ТОП-10 СОПЕРНИКОВ:")
        print("  Соперник              | Игры | Победы | Поражения | Ничьи | Точность")
        print("  " + "-" * 70)
        
        opponents = self.get_top_opponents(10)
        for opp in opponents:
            name = opp['name'][:20] if opp['name'] else 'Unknown'
            win_pct = opp['wins'] / opp['games'] * 100 if opp['games'] > 0 else 0
            acc_str = f"{opp['avg_accuracy']:5.1f}%" if opp['avg_accuracy'] else "  N/A"
            print(f"  {name:20s} | {opp['games']:4d} | {opp['wins']:4d} ({win_pct:5.1f}%) | {opp['losses']:7d} | {opp['draws']:5d} | {acc_str}")
        
        # Топ дебютов
        print("\n📖 ТОП-10 ДЕБЮТОВ:")
        print("  Дебют                | Игры | Победы | Поражения | Ничьи | Точность")
        print("  " + "-" * 70)
        
        openings = self.get_top_openings(10)
        for op in openings:
            name = op['name'][:20] if op['name'] else 'Unknown'
            win_pct = op['wins'] / op['games'] * 100 if op['games'] > 0 else 0
            acc_str = f"{op['avg_accuracy']:5.1f}%" if op['avg_accuracy'] else "  N/A"
            print(f"  {name:20s} | {op['games']:4d} | {op['wins']:4d} ({win_pct:5.1f}%) | {op['losses']:7d} | {op['draws']:5d} | {acc_str}")
        
        # Ежемесячная статистика
        print("\n📅 ЕЖЕМЕСЯЧНАЯ СТАТИСТИКА (последние 6 месяцев):")
        print("  Месяц    | Игры | Победы | Поражения | Ничьи | Точность | Рейтинг")
        print("  " + "-" * 70)
        
        monthly = self.get_monthly_stats()[:6]
        for ms in monthly:
            month_str = ms['month'].strftime('%Y-%m')
            win_pct = ms['wins'] / ms['games'] * 100 if ms['games'] > 0 else 0
            acc_str = f"{ms['avg_accuracy']:5.1f}%" if ms['avg_accuracy'] else "  N/A"
            print(f"  {month_str} | {ms['games']:4d} | {ms['wins']:4d} ({win_pct:5.1f}%) | {ms['losses']:7d} | {ms['draws']:5d} | {acc_str} | {ms['avg_rating']:6.0f}")
        
        print("\n" + "=" * 70)
        
        # Последние игры
        print("\n📋 ПОСЛЕДНИЕ 5 ИГР:")
        print("  Дата       | Рейтинг | Результат | Точность | Соперник")
        print("  " + "-" * 65)
        
        recent = self.get_rating_progression(5)
        for game in recent:
            date_str = game['date'].strftime('%Y-%m-%d')
            result_emoji = "✅" if game['result'] == 'Win' else "❌" if game['result'] == 'Loss' else "➖"
            acc_str = f"{game['accuracy']:5.1f}%" if game['accuracy'] else "  N/A"
            print(f"  {date_str} | {game['my_rating']:6d} | {game['result']:6s} {result_emoji} | {acc_str} | {game['opponent_rating']:6d}")
        
        print("\n" + "=" * 70)


def list_players():
    """Показывает список всех игроков в БД"""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    
    print("\n📋 СПИСОК ИГРОКОВ В БАЗЕ ДАННЫХ:")
    print("=" * 50)
    
    with db.connection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name LIKE 'games_%'
                ORDER BY table_name;
            """)
            
            players = []
            for row in cur.fetchall():
                # Извлекаем имя из названия таблицы
                player_name = row[0][6:]  # Убираем 'games_'
                
                # Получаем количество игр
                cur.execute(f"SELECT COUNT(*) FROM {row[0]}")
                count = cur.fetchone()[0]
                
                players.append((player_name, count))
    
    if players:
        print("\n  Игрок                  | Игр")
        print("  " + "-" * 35)
        for name, count in players:
            print(f"  {name:20s} | {count:4d}")
    else:
        print("  ❌ Нет данных о других игроках")
        print("\n  Чтобы добавить игрока, скачайте его игры:")
        print("  python scripts/04_download_player_games.py --username 'Имя'")
    
    db.close()


def main():
    parser = argparse.ArgumentParser(description='Анализ игр другого игрока')
    parser.add_argument('--username', '-u', type=str,
                       help='Имя пользователя для анализа')
    parser.add_argument('--list', '-l', action='store_true',
                       help='Показать список всех доступных игроков в БД')
    parser.add_argument('--detailed', '-d', action='store_true',
                       help='Показать детальную статистику')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Подробный вывод')
    
    args = parser.parse_args()
    
    try:
        # Если нужно показать список игроков
        if args.list:
            list_players()
            return
        
        # Если не указан username
        if not args.username:
            parser.print_help()
            print("\n❌ Укажите --username для анализа или --list для списка игроков")
            sys.exit(1)
        
        # Анализ конкретного игрока
        analyzer = PlayerAnalyzer(args.username)
        
        # Проверяем существование таблицы
        if not analyzer.table_exists():
            print(f"❌ Игрок '{args.username}' не найден в БД!")
            print("\nСначала скачайте его игры:")
            print(f"  python scripts/04_download_player_games.py --username '{args.username}'")
            analyzer.close()
            sys.exit(1)
        
        # Выводим отчет
        analyzer.print_report(detailed=args.detailed)
        
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