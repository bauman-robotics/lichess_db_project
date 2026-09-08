#!/usr/bin/env python3
"""
Анализ дебютов с поддержкой разных игроков
"""
import sys
import argparse
from pathlib import Path
from tabulate import tabulate

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager


def get_table_name(username: str = None) -> str:
    """Возвращает имя таблицы для игрока или основную таблицу"""
    if username:
        return f"games_{username.lower()}"
    return "games"


def get_all_openings(db, table_name: str, limit: int = 30, min_games: int = 3) -> list:
    """Получает список всех дебютов с их популярностью"""
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
                WHERE opening_name IS NOT NULL
                GROUP BY opening_name
                HAVING COUNT(*) >= %s
                ORDER BY games DESC
                LIMIT %s;
            """, (min_games, limit))
            
            return [{
                'name': row[0],
                'games': row[1],
                'wins': row[2],
                'losses': row[3],
                'draws': row[4],
                'accuracy': row[5] if row[5] else 0
            } for row in cur.fetchall()]


def search_openings(db, table_name: str, search_term: str, min_games: int = 1) -> list:
    """Ищет дебюты по названию"""
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
                WHERE opening_name ILIKE %s
                GROUP BY opening_name
                HAVING COUNT(*) >= %s
                ORDER BY games DESC;
            """, (f"%{search_term}%", min_games))
            
            return [{
                'name': row[0],
                'games': row[1],
                'wins': row[2],
                'losses': row[3],
                'draws': row[4],
                'accuracy': row[5] if row[5] else 0
            } for row in cur.fetchall()]


def analyze_opening(db, table_name: str, opening_name: str, player_name: str = None):
    """Детальный анализ конкретного дебюта"""
    display_name = player_name if player_name else "ваших"
    print(f"\n📖 ДЕТАЛЬНЫЙ АНАЛИЗ ДЕБЮТА: {opening_name}")
    print(f"👤 Игрок: {display_name}")
    print("=" * 70)
    
    with db.connection.get_connection() as conn:
        with conn.cursor() as cur:
            
            # Общая статистика по дебюту
            cur.execute(f"""
                SELECT 
                    COUNT(*) as games,
                    SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN result = 'Loss' THEN 1 ELSE 0 END) as losses,
                    SUM(CASE WHEN result = 'Draw' THEN 1 ELSE 0 END) as draws,
                    ROUND(AVG(move_count), 1) as avg_moves,
                    ROUND(AVG(accuracy), 1) as avg_accuracy
                FROM {table_name}
                WHERE opening_name ILIKE %s;
            """, (f"%{opening_name}%",))
            
            row = cur.fetchone()
            if not row or row[0] == 0:
                print(f"❌ Дебют '{opening_name}' не найден")
                return
            
            games, wins, losses, draws, avg_moves, avg_accuracy = row
            
            print(f"\n📊 ОБЩАЯ СТАТИСТИКА:")
            print(f"  Всего игр: {games}")
            print(f"  Победы: {wins} ({wins/games*100:.1f}%)")
            print(f"  Поражения: {losses} ({losses/games*100:.1f}%)")
            print(f"  Ничьи: {draws} ({draws/games*100:.1f}%)")
            print(f"  Средняя длина: {avg_moves:.1f} ходов")
            if avg_accuracy:
                print(f"  Средняя точность: {avg_accuracy:.1f}%")
            
            # Статистика по цвету
            cur.execute(f"""
                SELECT 
                    player_color,
                    COUNT(*) as games,
                    SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN result = 'Loss' THEN 1 ELSE 0 END) as losses,
                    SUM(CASE WHEN result = 'Draw' THEN 1 ELSE 0 END) as draws
                FROM {table_name}
                WHERE opening_name ILIKE %s
                GROUP BY player_color;
            """, (f"%{opening_name}%",))
            
            print(f"\n🎯 СТАТИСТИКА ПО ЦВЕТУ:")
            for row in cur.fetchall():
                color, g, w, l, d = row
                color_name = "Белые" if color == 'white' else "Черные"
                win_pct = w / g * 100 if g > 0 else 0
                print(f"  {color_name}: {g} игр, {w} побед ({win_pct:.1f}%)")
            
            # Варианты дебюта
            cur.execute(f"""
                SELECT 
                    opening_name,
                    COUNT(*) as games,
                    SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN result = 'Loss' THEN 1 ELSE 0 END) as losses
                FROM {table_name}
                WHERE opening_name ILIKE %s
                GROUP BY opening_name
                ORDER BY games DESC;
            """, (f"%{opening_name}%",))
            
            variants = cur.fetchall()
            if len(variants) > 1:
                print(f"\n📋 ВАРИАНТЫ ДЕБЮТА:")
                for row in variants:
                    name, g, w, l = row
                    wp = w / g * 100 if g > 0 else 0
                    print(f"  {name[:50]:50s} | {g:3d} игр | {wp:5.1f}% побед")
            
            # Последние игры
            cur.execute(f"""
                SELECT 
                    game_date,
                    opponent_name,
                    player_color,
                    result,
                    move_count,
                    accuracy
                FROM {table_name}
                WHERE opening_name ILIKE %s
                ORDER BY game_date DESC
                LIMIT 10;
            """, (f"%{opening_name}%",))
            
            print(f"\n📋 ПОСЛЕДНИЕ 10 ИГР ЭТИМ ДЕБЮТОМ:")
            print("  Дата       | Цвет    | Соперник            | Результат | Ходов | Точность")
            print("  " + "-" * 80)
            
            for row in cur.fetchall():
                date_str = row[0].strftime('%Y-%m-%d')
                color = "⚪" if row[2] == 'white' else "⚫"
                emoji = "✅" if row[3] == 'Win' else "❌" if row[3] == 'Loss' else "➖"
                acc_str = f"{row[5]:.1f}%" if row[5] else "N/A"
                print(f"  {date_str} | {color}      | {row[1][:20]:20s} | {row[3]:6s} {emoji} | {row[4]:4d} | {acc_str}")


def show_openings_list(db, table_name: str, limit: int = 30, search_term: str = None, 
                       player_name: str = None, min_games: int = 3):
    """Показывает список дебютов"""
    if search_term:
        openings = search_openings(db, table_name, search_term, min_games)
        print(f"\n🔍 РЕЗУЛЬТАТЫ ПОИСКА: '{search_term}' (минимум {min_games} игр)")
    else:
        openings = get_all_openings(db, table_name, limit, min_games)
        print(f"\n📋 СПИСОК ПОПУЛЯРНЫХ ДЕБЮТОВ (топ {limit}, минимум {min_games} игр)")
    
    if player_name:
        print(f"👤 Игрок: {player_name}")
    
    if not openings:
        print("❌ Дебюты не найдены")
        return
    
    print("=" * 80)
    
    # Формируем таблицу
    table = []
    for i, op in enumerate(openings, 1):
        win_pct = op['wins'] / op['games'] * 100 if op['games'] > 0 else 0
        acc_str = f"{op['accuracy']:.1f}%" if op['accuracy'] else "N/A"
        table.append([
            i,
            op['name'][:35],
            op['games'],
            f"{win_pct:.1f}%",
            acc_str,
            f"Поражений: {op['losses']}"
        ])
    
    print(tabulate(table, 
                   headers=['#', 'Дебют', 'Игры', 'Победы', 'Точность', 'Примечание'],
                   tablefmt='grid',
                   maxcolwidths=[4, 35, 6, 8, 10, 20]))
    
    print(f"\n💡 Для детального анализа введите: python scripts/03_analyze_opening.py --analyze 'Название дебюта'")


def show_help():
    """Показывает справку"""
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    АНАЛИЗ ДЕБЮТОВ - КОНСОЛЬНАЯ СПРАВКА                      ║
╚══════════════════════════════════════════════════════════════════════════════╝

📌 ОСНОВНЫЕ КОМАНДЫ:

  # Анализ своих игр (таблица games)
  python scripts/03_analyze_opening.py --list
  python scripts/03_analyze_opening.py --search "Caro-Kann"
  python scripts/03_analyze_opening.py --analyze "Pirc Defense"

  # Анализ игр другого игрока
  python scripts/03_analyze_opening.py --player "xxxxxxx" --list
  python scripts/03_analyze_opening.py --player "xxxxxxx" --search "Sicilian"
  python scripts/03_analyze_opening.py --player "xxxxxxx" --analyze "Rapport-Jobava"

  # Дополнительные опции
  python scripts/03_analyze_opening.py --list --limit 50
  python scripts/03_analyze_opening.py --player "xxxxxxx" --list --limit 20
  python scripts/03_analyze_opening.py --list --min-games 1  # Показать все дебюты

📊 ЧТО ПОКАЗЫВАЕТ АНАЛИЗ ДЕБЮТА:
  • Общая статистика (игры, победы, поражения, ничьи)
  • Процент побед по цвету (белые/черные)
  • Варианты дебюта
  • Последние 10 игр этим дебютом

💡 РЕКОМЕНДАЦИИ:
  1. Изучайте дебюты с низким процентом побед
  2. Смотрите последние игры для анализа ошибок
  3. Сравнивайте варианты одного дебюта
  4. Обращайте внимание на точность игры

📚 ПОПУЛЯРНЫЕ ДЕБЮТЫ ДЛЯ АНАЛИЗА:
  • Caro-Kann Defense
  • Queen's Gambit Declined
  • Slav Defense
  • Sicilian Defense
  • Pirc Defense (нужно улучшить!)
  • King's Gambit Declined (нужно улучшить!)

════════════════════════════════════════════════════════════════════════════════
""")


def main():
    parser = argparse.ArgumentParser(
        description='Анализ дебютов с поддержкой разных игроков',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  # Свои игры
  python scripts/03_analyze_opening.py --list
  python scripts/03_analyze_opening.py --search "Caro"
  python scripts/03_analyze_opening.py --analyze "Pirc Defense"
  
  # Игры другого игрока
  python scripts/03_analyze_opening.py --player "xxxxxxx" --list
  python scripts/03_analyze_opening.py --player "xxxxxxx" --analyze "Rapport-Jobava"
  
  # Показать все дебюты (даже с 1 игрой)
  python scripts/03_analyze_opening.py --list --min-games 1
        """
    )
    
    parser.add_argument('--player', '-p', type=str,
                       help='Имя игрока для анализа (если не указан - свои игры)')
    
    parser.add_argument('--list', '-l', action='store_true',
                       help='Показать список популярных дебютов')
    
    parser.add_argument('--limit', '-L', type=int, default=30,
                       help='Количество дебютов в списке (по умолчанию 30)')
    
    parser.add_argument('--search', '-s', type=str,
                       help='Поиск дебютов по ключевому слову')
    
    parser.add_argument('--analyze', '-a', type=str,
                       help='Детальный анализ конкретного дебюта')
    
    parser.add_argument('--min-games', '-m', type=int, default=3,
                       help='Минимальное количество игр для отображения (по умолчанию 3)')

    args = parser.parse_args()
    
    # Если нет аргументов, показываем справку
    if len(sys.argv) == 1:
        show_help()
        return
    
    try:
        config = ConfigLoader()
        db = DatabaseManager(config, 'local')
        
        # Определяем таблицу
        table_name = get_table_name(args.player)
        
        # Проверяем существование таблицы
        original_table = db.table_name
        db.table_name = table_name
        
        if not db.table_exists():
            if args.player:
                print(f"❌ Игрок '{args.player}' не найден в БД!")
                print(f"\nСначала скачайте его игры:")
                print(f"  python scripts/04_download_player_games.py --username '{args.player}'")
            else:
                print("❌ Таблица games не найдена!")
                print("Сначала создайте таблицу:")
                print("  python scripts/setup_db.py --action create")
            db.close()
            sys.exit(1)
        
        # Восстанавливаем имя таблицы
        db.table_name = original_table
        
        # Выполняем действие
        if args.list:
            show_openings_list(db, table_name, args.limit, player_name=args.player, min_games=args.min_games)
        
        elif args.search:
            show_openings_list(db, table_name, search_term=args.search, player_name=args.player, min_games=args.min_games)
        
        elif args.analyze:
            analyze_opening(db, table_name, args.analyze, args.player)
        
        else:
            show_help()
        
        db.close()
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Прервано пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()