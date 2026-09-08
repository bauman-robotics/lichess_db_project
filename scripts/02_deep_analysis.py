#!/usr/bin/env python3
"""
Глубокий анализ игр с поддержкой разных игроков


# Общий отчет по играм Магнуса
python3 scripts/01_analyze_games.py

# Анализ дебютов Магнуса
python3 scripts/03_analyze_opening.py --list

# Анализ конкретного дебюта (например, его любимый)
python3 scripts/03_analyze_opening.py --analyze "Sicilian Defense"

# Анализ своих игр (таблица games)
python3 scripts/02_deep_analysis.py

# Анализ игр другого игрока
python3 scripts/02_deep_analysis.py --player "xxxxxxx"

# С подробным выводом ошибок
python3 scripts/02_deep_analysis.py --player "xxxxxxx" --verbose

"""
import sys
import argparse
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager


def get_table_name(username: str = None) -> str:
    """Возвращает имя таблицы для игрока или основную таблицу"""
    if username:
        return f"games_{username.lower()}"
    return "games"


def analyze_player(username: str = None):
    """Глубокий анализ игр"""
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    
    # Определяем таблицу
    table_name = get_table_name(username)
    display_name = username if username else "ваших"
    
    # Проверяем существование таблицы
    original_table = db.table_name
    db.table_name = table_name
    
    if not db.table_exists():
        if username:
            print(f"❌ Игрок '{username}' не найден в БД!")
            print(f"\nСначала скачайте его игры:")
            print(f"  python scripts/04_download_player_games.py --username '{username}'")
        else:
            print("❌ Таблица games не найдена!")
            print("Сначала создайте таблицу:")
            print("  python scripts/setup_db.py --action create")
        db.close()
        return
    
    # Восстанавливаем имя таблицы
    db.table_name = original_table
    
    print("\n" + "=" * 70)
    print(f"🎯 ГЛУБОКИЙ АНАЛИЗ ИГР ИГРОКА: {display_name}")
    print("=" * 70)
    
    with db.connection.get_connection() as conn:
        with conn.cursor() as cur:
            
            # 1. Анализ по времени контроля
            print("\n⏰ СТАТИСТИКА ПО КОНТРОЛЮ ВРЕМЕНИ:")
            print("  Контроль | Игры | Победы | % побед")
            print("  " + "-" * 45)
            
            cur.execute(f"""
                SELECT 
                    time_control,
                    COUNT(*) as games,
                    SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins
                FROM {table_name}
                GROUP BY time_control
                ORDER BY games DESC
                LIMIT 5;
            """)
            
            rows = cur.fetchall()
            if rows:
                for row in rows:
                    win_pct = row[2] / row[1] * 100 if row[1] > 0 else 0
                    print(f"  {row[0]:10s} | {row[1]:4d} | {row[2]:4d} | {win_pct:5.1f}%")
            else:
                print("  Нет данных")
            
            # 2. Игры против более сильных и слабых соперников
            print("\n🎯 РЕЗУЛЬТАТЫ ПРОТИВ СОПЕРНИКОВ ПО РЕЙТИНГУ:")
            print("  Категория      | Игры | Победы | % побед")
            print("  " + "-" * 50)
            
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
                WHERE opponent_rating > 0 AND my_rating > 0
                GROUP BY category
                ORDER BY games DESC;
            """)
            
            rows = cur.fetchall()
            if rows:
                for row in rows:
                    win_pct = row[2] / row[1] * 100 if row[1] > 0 else 0
                    print(f"  {row[0]:15s} | {row[1]:4d} | {row[2]:4d} | {win_pct:5.1f}%")
            else:
                print("  Нет данных")
            
            # 3. Анализ длины партий
            print("\n📏 АНАЛИЗ ДЛИНЫ ПАРТИЙ:")
            print("  Диапазон      | Игры | Победы | % побед")
            print("  " + "-" * 50)
            
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
                ORDER BY games DESC;
            """)
            
            rows = cur.fetchall()
            if rows:
                for row in rows:
                    win_pct = row[2] / row[1] * 100 if row[1] > 0 else 0
                    print(f"  {row[0]:15s} | {row[1]:4d} | {row[2]:4d} | {win_pct:5.1f}%")
            else:
                print("  Нет данных")
            
            # 4. Лучшие победы (против самых сильных соперников)
            print("\n🏆 ЛУЧШИЕ ПОБЕДЫ (против самых сильных соперников):")
            print("  Соперник              | Рейтинг | Дата")
            print("  " + "-" * 50)
            
            cur.execute(f"""
                SELECT 
                    opponent_name,
                    opponent_rating,
                    game_date
                FROM {table_name}
                WHERE result = 'Win' AND opponent_rating > 1500
                ORDER BY opponent_rating DESC
                LIMIT 10;
            """)
            
            rows = cur.fetchall()
            if rows:
                for row in rows:
                    date_str = row[2].strftime('%Y-%m-%d')
                    print(f"  {row[0][:20]:20s} | {row[1]:6d} | {date_str}")
            else:
                print("  Нет побед над сильными соперниками")
            
            # 5. Дебюты с наибольшим процентом поражений
            print("\n⚠️ ДЕБЮТЫ С НАИБОЛЬШИМ ПРОЦЕНТОМ ПОРАЖЕНИЙ (> 50%):")
            print("  Дебют                | Игры | Поражения | % поражений")
            print("  " + "-" * 65)
            
            cur.execute(f"""
                SELECT 
                    opening_name,
                    COUNT(*) as games,
                    SUM(CASE WHEN result = 'Loss' THEN 1 ELSE 0 END) as losses
                FROM {table_name}
                WHERE opening_name IS NOT NULL
                GROUP BY opening_name
                HAVING COUNT(*) >= 3 AND SUM(CASE WHEN result = 'Loss' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) > 0.5
                ORDER BY losses DESC
                LIMIT 10;
            """)
            
            rows = cur.fetchall()
            if rows:
                for row in rows:
                    loss_pct = row[2] / row[1] * 100 if row[1] > 0 else 0
                    name = row[0][:20] if row[0] else 'Unknown'
                    print(f"  {name:20s} | {row[1]:4d} | {row[2]:4d} | {loss_pct:5.1f}%")
            else:
                print("  Нет дебютов с >50% поражений")
            
            # 6. Дебюты с наибольшим процентом побед
            print("\n🏆 ДЕБЮТЫ С НАИБОЛЬШИМ ПРОЦЕНТОМ ПОБЕД (> 50%):")
            print("  Дебют                | Игры | Победы | % побед")
            print("  " + "-" * 65)
            
            cur.execute(f"""
                SELECT 
                    opening_name,
                    COUNT(*) as games,
                    SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins
                FROM {table_name}
                WHERE opening_name IS NOT NULL
                GROUP BY opening_name
                HAVING COUNT(*) >= 3 AND SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) * 1.0 / COUNT(*) > 0.5
                ORDER BY wins DESC
                LIMIT 10;
            """)
            
            rows = cur.fetchall()
            if rows:
                for row in rows:
                    win_pct = row[2] / row[1] * 100 if row[1] > 0 else 0
                    name = row[0][:20] if row[0] else 'Unknown'
                    print(f"  {name:20s} | {row[1]:4d} | {row[2]:4d} | {win_pct:5.1f}%")
            else:
                print("  Нет дебютов с >50% побед")
            
            # 7. Динамика рейтинга по месяцам
            print("\n📈 ДИНАМИКА РЕЙТИНГА ПО МЕСЯЦАМ:")
            print("  Месяц    | Рейтинг | Изменение")
            print("  " + "-" * 40)
            
            cur.execute(f"""
                WITH monthly_rating AS (
                    SELECT 
                        DATE_TRUNC('month', game_date) as month,
                        AVG(my_rating) as avg_rating
                    FROM {table_name}
                    GROUP BY month
                    ORDER BY month
                )
                SELECT 
                    month,
                    avg_rating,
                    LAG(avg_rating) OVER (ORDER BY month) as prev_rating
                FROM monthly_rating;
            """)
            
            rows = cur.fetchall()
            if rows:
                for row in rows:
                    month_str = row[0].strftime('%Y-%m')
                    change = row[1] - row[2] if row[2] else 0
                    change_str = f"+{change:.0f}" if change > 0 else f"{change:.0f}"
                    print(f"  {month_str} | {row[1]:6.0f} | {change_str:8s}")
            else:
                print("  Нет данных")
            
            # 8. Общая статистика
            print("\n📊 ОБЩАЯ СТАТИСТИКА:")
            cur.execute(f"""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN result = 'Win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN result = 'Loss' THEN 1 ELSE 0 END) as losses,
                    SUM(CASE WHEN result = 'Draw' THEN 1 ELSE 0 END) as draws,
                    ROUND(AVG(accuracy), 1) as avg_accuracy
                FROM {table_name}
            """)
            
            row = cur.fetchone()
            if row and row[0] > 0:
                total, wins, losses, draws, avg_accuracy = row
                win_pct = wins / total * 100 if total > 0 else 0
                loss_pct = losses / total * 100 if total > 0 else 0
                draw_pct = draws / total * 100 if total > 0 else 0
                
                print(f"  Всего игр: {total}")
                print(f"  Победы: {wins} ({win_pct:.1f}%)")
                print(f"  Поражения: {losses} ({loss_pct:.1f}%)")
                print(f"  Ничьи: {draws} ({draw_pct:.1f}%)")
                if avg_accuracy:
                    print(f"  Средняя точность: {avg_accuracy:.1f}%")
            else:
                print("  Нет данных")
    
    db.close()
    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description='Глубокий анализ игр с поддержкой разных игроков',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  # Анализ своих игр
  python scripts/02_deep_analysis.py
  
  # Анализ игр другого игрока
  python scripts/02_deep_analysis.py --player "xxxxx"
  
  # Анализ с подробным выводом
  python scripts/02_deep_analysis.py --player "xxxxx" --verbose
        """
    )
    
    parser.add_argument('--player', '-p', type=str,
                       help='Имя игрока для анализа (если не указан - свои игры)')
    
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Подробный вывод')
    
    args = parser.parse_args()
    
    try:
        analyze_player(args.player)
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