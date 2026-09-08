#!/usr/bin/env python3
"""
Просмотр всех таблиц в базе данных
"""
import sys
from pathlib import Path
from tabulate import tabulate

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager


def main():
    config = ConfigLoader()
    db = DatabaseManager(config, 'local')
    
    print("\n📋 СПИСОК ВСЕХ ТАБЛИЦ В БАЗЕ ДАННЫХ")
    print("=" * 60)
    
    with db.connection.get_connection() as conn:
        with conn.cursor() as cur:
            # Получаем список всех таблиц
            cur.execute("""
                SELECT 
                    table_name,
                    (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = t.table_name) as columns
                FROM information_schema.tables t
                WHERE table_schema = 'public'
                ORDER BY 
                    CASE 
                        WHEN table_name = 'games' THEN 1
                        WHEN table_name LIKE 'games_%' THEN 2
                        ELSE 3
                    END,
                    table_name;
            """)
            
            tables = cur.fetchall()
            
            if not tables:
                print("❌ Таблицы не найдены")
                db.close()
                return
            
            # Собираем данные
            table_data = []
            for table_name, columns in tables:
                # Получаем количество записей
                cur.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cur.fetchone()[0]
                
                # Определяем тип таблицы
                if table_name == 'games':
                    table_type = "📊 Основная"
                elif table_name.startswith('games_'):
                    table_type = "👤 Игрок"
                else:
                    table_type = "📁 Другая"
                
                table_data.append([
                    table_type,
                    table_name,
                    columns,
                    count
                ])
            
            # Выводим таблицу
            print(tabulate(table_data, 
                          headers=['Тип', 'Таблица', 'Колонок', 'Записей'],
                          tablefmt='grid',
                          maxcolwidths=[10, 30, 10, 10]))
            
            # Дополнительная информация
            print("\n📊 СТАТИСТИКА:")
            total_records = sum(row[3] for row in table_data)
            total_tables = len(table_data)
            
            print(f"  Всего таблиц: {total_tables}")
            print(f"  Всего записей: {total_records}")
            
            # Игроки в базе
            player_tables = [row for row in table_data if row[1].startswith('games_')]
            if player_tables:
                print(f"\n👥 Игроки в базе данных:")
                for row in player_tables:
                    player_name = row[1][6:]  # Убираем 'games_'
                    print(f"  • {player_name}: {row[3]} игр")
            else:
                print("\n👥 Нет данных о других игроках")
    
    db.close()


if __name__ == '__main__':
    main()