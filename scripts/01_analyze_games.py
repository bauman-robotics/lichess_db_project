#!/usr/bin/env python3
"""
Скрипт для анализа шахматных игр из базы данных
Поддерживает анализ своих игр и игр других игроков


# Анализ своих игр
python3 scripts/01_analyze_games.py

# Анализ игр другого игрока
python3 scripts/01_analyze_games.py --player "xxxxx"

# Детальный анализ с распределением точности
python3 scripts/01_analyze_games.py --detailed
python3 scripts/01_analyze_games.py --player "xxxxx" --detailed

# Указать количество соперников и дебютов
python3 scripts/01_analyze_games.py --opponents 20 --openings 15

# С подробным выводом ошибок
python3 scripts/01_analyze_games.py --player "xxxxx" --verbose

"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import argparse

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager


def get_table_name(username: str = None) -> str:
    """Возвращает имя таблицы для игрока или основную таблицу"""
    if username:
        return f"games_{username.lower()}"
    return "games"


class GameAnalyzer:
    """Анализатор шахматных игр"""
    
    def __init__(self, username: Optional[str] = None):
        """
        Инициализация анализатора
        
        Args:
            username: Имя игрока для анализа (если None - свои игры)
        """
        self.username = username
        self.table_name = get_table_name(username)
        self.display_name = username if username else "ваших"
        
        self.config = ConfigLoader()
        self.db = DatabaseManager(self.config, 'local')
        
        # Подменяем таблицу
        original_table = self.db.table_name
        self.db.table_name = self.table_name
        
        # Проверяем существование таблицы
        if not self.db.table_exists():
            if username:
                raise Exception(f"Игрок '{username}' не найден в БД! Сначала скачайте его игры.")
            else:
                raise Exception("Таблица games не найдена! Сначала создайте таблицу.")
        
        # Восстанавливаем имя таблицы
        self.db.table_name = original_table
        
        self.total_games = 0
        
    def close(self):
        """Закрывает подключение к БД"""
        self.db.close()
    
    def get_basic_stats(self) -> Dict:
        """Базовая статистика"""
        # Подменяем таблицу для запроса
        original_table = self.db.table_name
        self.db.table_name = self.table_name
        
        stats = self.db.get_table_stats()
        self.total_games = stats.get('total_records', 0)
        
        # Восстанавливаем
        self.db.table_name = original_table
        
        result_dist = {}
        for result, count in stats.get('results_distribution', []):
            result_dist[result] = count
        
        # Получаем среднюю точность только если есть данные
        avg_accuracy = stats.get('avg_accuracy')
        if avg_accuracy is None and self.total_games > 0:
            # Попробуем вычислить вручную
            with self.db.connection.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT AVG(accuracy) FROM {self.table_name} WHERE accuracy IS NOT NULL")
                    avg_accuracy = cur.fetchone()[0]
        
        return {
            'total': self.total_games,
            'first_game': stats.get('first_game'),
            'last_game': stats.get('last_game'),
            'unique_opponents': stats.get('unique_opponents', 0),
            'avg_accuracy': avg_accuracy,
            'results': result_dist,
            'wins': result_dist.get('Win', 0),
            'losses': result_dist.get('Loss', 0),
            'draws': result_dist.get('Draw', 0)
        }
    
    def get_stats_by_color(self) -> List[Dict]:
        """Статистика по цвету фигур"""
        with self.db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT 
                        player_color,
                        COUNT(*) as games,
                        SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN result = 'Loss' THEN 1 ELSE 0 END) as losses,
                        SUM(CASE WHEN result = 'Draw' THEN 1 ELSE 0 END) as draws,
                        ROUND(AVG(accuracy), 1) as avg_accuracy,
                        ROUND(AVG(move_count), 1) as avg_moves
                    FROM {self.table_name}
                    GROUP BY player_color;
                """)
                
                return [{
                    'color': row[0],
                    'games': row[1],
                    'wins': row[2],
                    'losses': row[3],
                    'draws': row[4],
                    'avg_accuracy': row[5] if row[5] else 0,
                    'avg_moves': row[6] if row[6] else 0
                } for row in cur.fetchall()]
    
    def get_top_opponents(self, limit: int = 10) -> List[Dict]:
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
    
    def get_top_openings(self, limit: int = 10) -> List[Dict]:
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
    
    def get_rating_progression(self, limit: int = 30) -> List[Dict]:
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
    
    def get_monthly_stats(self) -> List[Dict]:
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
    
    def get_accuracy_distribution(self) -> Dict:
        """Распределение точности"""
        with self.db.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT 
                        CASE 
                            WHEN accuracy >= 90 THEN '90-100%'
                            WHEN accuracy >= 80 THEN '80-89%'
                            WHEN accuracy >= 70 THEN '70-79%'
                            WHEN accuracy >= 60 THEN '60-69%'
                            WHEN accuracy >= 50 THEN '50-59%'
                            ELSE '0-49%'
                        END as range,
                        COUNT(*) as count
                    FROM {self.table_name}
                    WHERE accuracy IS NOT NULL
                    GROUP BY range
                    ORDER BY range DESC;
                """)
                
                return {row[0]: row[1] for row in cur.fetchall()}
    
    def print_report(self, detailed: bool = False):
        """Печатает полный отчет"""
        print("\n" + "=" * 70)
        print(f"📊 ОТЧЕТ ПО ИГРАМ ИГРОКА: {self.display_name}")
        print("=" * 70)
        
        # Базовая статистика
        stats = self.get_basic_stats()
        print(f"\n📅 Всего игр: {stats['total']}")
        print(f"📅 Период: {stats['first_game']} - {stats['last_game']}")
        print(f"👥 Уникальных соперников: {stats['unique_opponents']}")
        
        # Проверяем, есть ли данные о точности
        if stats['avg_accuracy'] is not None:
            print(f"🎯 Средняя точность: {stats['avg_accuracy']:.1f}%")
        else:
            print("🎯 Средняя точность: Нет данных")
        
        if stats['total'] > 0:
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
        if color_stats:
            for cs in color_stats:
                color_name = "Белые" if cs['color'] == 'white' else "Черные"
                win_pct = cs['wins'] / cs['games'] * 100 if cs['games'] > 0 else 0
                acc_str = f"{cs['avg_accuracy']:5.1f}%" if cs['avg_accuracy'] else "  N/A"
                print(f"  {color_name:7s} | {cs['games']:4d} | {cs['wins']:5d} ({win_pct:5.1f}%) | {cs['losses']:7d} | {cs['draws']:5d} | {acc_str}")
        else:
            print("  Нет данных")
        
        # Топ соперников
        print("\n🏆 ТОП-10 СОПЕРНИКОВ:")
        print("  Соперник              | Игры | Победы | Поражения | Ничьи | Точность")
        print("  " + "-" * 70)
        
        opponents = self.get_top_opponents(10)
        if opponents:
            for opp in opponents:
                name = opp['name'][:20] if opp['name'] else 'Unknown'
                win_pct = opp['wins'] / opp['games'] * 100 if opp['games'] > 0 else 0
                acc_str = f"{opp['avg_accuracy']:5.1f}%" if opp['avg_accuracy'] else "  N/A"
                print(f"  {name:20s} | {opp['games']:4d} | {opp['wins']:4d} ({win_pct:5.1f}%) | {opp['losses']:7d} | {opp['draws']:5d} | {acc_str}")
        else:
            print("  Нет данных (минимум 3 игры с соперником)")
        
        # Топ дебютов
        print("\n📖 ТОП-10 ДЕБЮТОВ:")
        print("  Дебют                | Игры | Победы | Поражения | Ничьи | Точность")
        print("  " + "-" * 70)
        
        openings = self.get_top_openings(10)
        if openings:
            for op in openings:
                name = op['name'][:20] if op['name'] else 'Unknown'
                win_pct = op['wins'] / op['games'] * 100 if op['games'] > 0 else 0
                acc_str = f"{op['avg_accuracy']:5.1f}%" if op['avg_accuracy'] else "  N/A"
                print(f"  {name:20s} | {op['games']:4d} | {op['wins']:4d} ({win_pct:5.1f}%) | {op['losses']:7d} | {op['draws']:5d} | {acc_str}")
        else:
            print("  Нет данных (минимум 3 игры дебютом)")
        
        # Ежемесячная статистика
        print("\n📅 ЕЖЕМЕСЯЧНАЯ СТАТИСТИКА (последние 6 месяцев):")
        print("  Месяц    | Игры | Победы | Поражения | Ничьи | Точность | Рейтинг")
        print("  " + "-" * 70)
        
        monthly = self.get_monthly_stats()[:6]
        if monthly:
            for ms in monthly:
                month_str = ms['month'].strftime('%Y-%m')
                win_pct = ms['wins'] / ms['games'] * 100 if ms['games'] > 0 else 0
                acc_str = f"{ms['avg_accuracy']:5.1f}%" if ms['avg_accuracy'] else "  N/A"
                print(f"  {month_str} | {ms['games']:4d} | {ms['wins']:4d} ({win_pct:5.1f}%) | {ms['losses']:7d} | {ms['draws']:5d} | {acc_str} | {ms['avg_rating']:6.0f}")
        else:
            print("  Нет данных")
        
        # Распределение точности
        if detailed:
            print("\n🎯 РАСПРЕДЕЛЕНИЕ ТОЧНОСТИ:")
            accuracy_dist = self.get_accuracy_distribution()
            if accuracy_dist:
                for range_name, count in sorted(accuracy_dist.items()):
                    pct = count / stats['total'] * 100 if stats['total'] > 0 else 0
                    bar = "█" * int(pct / 2)
                    print(f"  {range_name:8s}: {count:4d} ({pct:5.1f}%) {bar}")
            else:
                print("  Нет данных о точности")
        
        print("\n" + "=" * 70)
        
        # Последние игры
        print("\n📋 ПОСЛЕДНИЕ 5 ИГР:")
        print("  Дата       | Рейтинг | Результат | Точность")
        print("  " + "-" * 55)
        
        recent = self.get_rating_progression(5)
        if recent:
            for game in recent:
                date_str = game['date'].strftime('%Y-%m-%d')
                result_emoji = "✅" if game['result'] == 'Win' else "❌" if game['result'] == 'Loss' else "➖"
                acc_str = f"{game['accuracy']:5.1f}%" if game['accuracy'] else "  N/A"
                print(f"  {date_str} | {game['my_rating']:6d} | {game['result']:6s} {result_emoji} | {acc_str}")
        else:
            print("  Нет данных")
        
        print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description='Анализ шахматных игр',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  # Анализ своих игр
  python scripts/01_analyze_games.py
  
  # Анализ игр другого игрока
  python scripts/01_analyze_games.py --player "xxxxxxx"
  
  # Детальный анализ
  python scripts/01_analyze_games.py --detailed
  python scripts/01_analyze_games.py --player "xxxxxxx" --detailed
        """
    )
    
    parser.add_argument('--player', '-p', type=str,
                       help='Имя игрока для анализа (если не указан - свои игры)')
    
    parser.add_argument('--detailed', '-d', action='store_true',
                       help='Показать детальную статистику (распределение точности)')
    
    parser.add_argument('--opponents', '-o', type=int, default=10,
                       help='Количество соперников для отображения')
    
    parser.add_argument('--openings', '-O', type=int, default=10,
                       help='Количество дебютов для отображения')
    
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Подробный вывод ошибок')
    
    args = parser.parse_args()
    
    try:
        analyzer = GameAnalyzer(args.player)
        
        # Проверяем наличие данных
        stats = analyzer.get_basic_stats()
        if stats['total'] == 0:
            print(f"❌ Нет данных в таблице для игрока: {args.player if args.player else 'вас'}")
            if args.player:
                print(f"Сначала скачайте игры игрока:")
                print(f"  python scripts/04_download_player_games.py --username '{args.player}'")
            else:
                print("Сначала импортируйте игры:")
                print("  python scripts/import_games.py --source api --username DenNedelin")
            analyzer.close()
            sys.exit(1)
        
        # Выводим отчет
        analyzer.print_report(detailed=args.detailed)
        
        analyzer.close()
        
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        else:
            print("\nИспользуйте --verbose для детальной информации об ошибке")
        sys.exit(1)


if __name__ == '__main__':
    main()
