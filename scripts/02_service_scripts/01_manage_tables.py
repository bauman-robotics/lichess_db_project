#!/usr/bin/env python3
"""
Управление всеми таблицами в базе данных


🚀 Примеры использования:
1. Показать все таблицы
bash

python3 scripts/manage_tables.py --list

2. Удалить конкретную таблицу
bash

# Удалить основную таблицу
python3 scripts/manage_tables.py --drop --table games

# Удалить таблицу игрока
python3 scripts/manage_tables.py --drop --table games_xxxxxx

3. Удалить все таблицы игроков
bash

python3 scripts/manage_tables.py --drop --players

4. Удалить ВСЕ таблицы
bash

python3 scripts/manage_tables.py --drop --all

5. Очистить таблицу (удалить данные, сохранить структуру)
bash

python3 scripts/manage_tables.py --truncate --table games
python3 scripts/manage_tables.py --truncate --table games_xxxxxx

6. Очистить все таблицы игроков
bash

python3 scripts/manage_tables.py --truncate --players

7. Создать таблицу
bash

python3 scripts/manage_tables.py --create --table games

8. Без подтверждения (для автоматизации)
bash

python3 scripts/manage_tables.py --drop --table games --force
python3 scripts/manage_tables.py --drop --all --force

"""
import sys
import argparse
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.config_loader import ConfigLoader
from core.database.db_manager import DatabaseManager


def get_all_tables(db_manager) -> list:
    """Получает список всех таблиц в базе данных"""
    with db_manager.connection.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name NOT IN ('alembic_version', 'spatial_ref_sys')
                ORDER BY 
                    CASE 
                        WHEN table_name = 'games' THEN 0
                        WHEN table_name LIKE 'games_%' THEN 1
                        ELSE 2
                    END,
                    table_name;
            """)
            return [row[0] for row in cur.fetchall()]


def get_table_info(db_manager, table_name: str) -> dict:
    """Получает информацию о таблице"""
    original_table = db_manager.table_name
    db_manager.table_name = table_name
    
    info = {
        'name': table_name,
        'exists': db_manager.table_exists(),
        'records': 0
    }
    
    if info['exists']:
        stats = db_manager.get_table_stats()
        info['records'] = stats.get('total_records', 0)
    
    db_manager.table_name = original_table
    return info


def list_tables(db_manager):
    """Показывает все таблицы"""
    tables = get_all_tables(db_manager)
    
    print("\n" + "=" * 70)
    print("📋 ВСЕ ТАБЛИЦЫ В БАЗЕ ДАННЫХ")
    print("=" * 70)
    
    if not tables:
        print("❌ Таблицы не найдены")
        return
    
    print("\n  # | Таблица                | Записей | Тип")
    print("  " + "-" * 60)
    
    for i, table in enumerate(tables, 1):
        info = get_table_info(db_manager, table)
        table_type = "Основная" if table == 'games' else "Игрок" if table.startswith('games_') else "Другая"
        print(f"  {i:2d} | {table:22s} | {info['records']:8d} | {table_type}")
    
    print("\n" + "=" * 70)


def drop_table(db_manager, table_name: str, confirm: bool = True):
    """Удаляет таблицу"""
    info = get_table_info(db_manager, table_name)
    
    if not info['exists']:
        print(f"⚠️ Таблица {table_name} не существует")
        return False
    
    print(f"\n📋 Таблица: {table_name}")
    print(f"   Записей: {info['records']}")
    
    if confirm:
        response = input(f"  Удалить таблицу {table_name}? (y/N): ")
        if response.lower() != 'y':
            print("  ⏭️ Отменено")
            return False
    
    original_table = db_manager.table_name
    db_manager.table_name = table_name
    result = db_manager.drop_table()
    db_manager.table_name = original_table
    
    if result:
        print(f"  ✅ Таблица {table_name} удалена")
    else:
        print(f"  ❌ Ошибка удаления таблицы {table_name}")
    
    return result


def truncate_table(db_manager, table_name: str, confirm: bool = True):
    """Очищает таблицу (удаляет данные, сохраняя структуру)"""
    info = get_table_info(db_manager, table_name)
    
    if not info['exists']:
        print(f"⚠️ Таблица {table_name} не существует")
        return False
    
    if info['records'] == 0:
        print(f"✅ Таблица {table_name} уже пуста")
        return True
    
    print(f"\n📋 Таблица: {table_name}")
    print(f"   Записей: {info['records']}")
    
    if confirm:
        response = input(f"  Очистить таблицу {table_name} (удалить все {info['records']} записей)? (y/N): ")
        if response.lower() != 'y':
            print("  ⏭️ Отменено")
            return False
    
    original_table = db_manager.table_name
    db_manager.table_name = table_name
    
    try:
        with db_manager.connection.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f'TRUNCATE TABLE "{table_name}" RESTART IDENTITY CASCADE;')
                conn.commit()
        print(f"  ✅ Таблица {table_name} очищена")
        result = True
    except Exception as e:
        print(f"  ❌ Ошибка очистки таблицы: {e}")
        result = False
    
    db_manager.table_name = original_table
    return result


def create_table(db_manager, table_name: str, drop_existing: bool = False):
    """Создает таблицу"""
    original_table = db_manager.table_name
    db_manager.table_name = table_name
    
    result = db_manager.create_table(drop_existing=drop_existing)
    
    db_manager.table_name = original_table
    
    if result:
        print(f"  ✅ Таблица {table_name} создана")
    else:
        print(f"  ❌ Ошибка создания таблицы {table_name}")
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Управление таблицами в базе данных',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  # Показать все таблицы
  python scripts/manage_tables.py --list

  # Удалить таблицу
  python scripts/manage_tables.py --drop --table games
  python scripts/manage_tables.py --drop --table games_faarxa5a

  # Очистить таблицу (удалить данные)
  python scripts/manage_tables.py --truncate --table games

  # Создать таблицу
  python scripts/manage_tables.py --create --table games

  # Удалить все таблицы игроков
  python scripts/manage_tables.py --drop --players

  # Удалить все таблицы (включая основную)
  python scripts/manage_tables.py --drop --all

  # Без подтверждения
  python scripts/manage_tables.py --drop --table games --force
        """
    )
    
    parser.add_argument('--list', '-l', action='store_true',
                       help='Показать все таблицы')
    
    parser.add_argument('--table', '-t', type=str,
                       help='Имя таблицы для операции')
    
    parser.add_argument('--drop', '-d', action='store_true',
                       help='Удалить таблицу')
    
    parser.add_argument('--truncate', '-r', action='store_true',
                       help='Очистить таблицу (удалить данные)')
    
    parser.add_argument('--create', '-c', action='store_true',
                       help='Создать таблицу')
    
    parser.add_argument('--players', '-p', action='store_true',
                       help='Применить ко всем таблицам игроков (games_*)')
    
    parser.add_argument('--all', '-a', action='store_true',
                       help='Применить ко всем таблицам')
    
    parser.add_argument('--force', '-f', action='store_true',
                       help='Без подтверждения')
    
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Подробный вывод')
    
    args = parser.parse_args()
    
    try:
        config = ConfigLoader()
        db_manager = DatabaseManager(config, 'local')
        
        # Показываем список таблиц
        if args.list or (len(sys.argv) == 1):
            list_tables(db_manager)
            db_manager.close()
            return
        
        # Получаем список таблиц для обработки
        tables_to_process = []
        
        if args.table:
            tables_to_process = [args.table]
        elif args.players:
            # Все таблицы игроков
            all_tables = get_all_tables(db_manager)
            tables_to_process = [t for t in all_tables if t.startswith('games_')]
            if not tables_to_process:
                print("❌ Нет таблиц игроков")
                db_manager.close()
                return
        elif args.all:
            tables_to_process = get_all_tables(db_manager)
            if not tables_to_process:
                print("❌ Нет таблиц для обработки")
                db_manager.close()
                return
        else:
            print("❌ Укажите --table, --players или --all")
            db_manager.close()
            sys.exit(1)
        
        # Выполняем операции
        if args.drop:
            print("\n" + "=" * 70)
            print("🗑️ УДАЛЕНИЕ ТАБЛИЦ")
            print("=" * 70)
            for table in tables_to_process:
                drop_table(db_manager, table, confirm=not args.force)
        
        elif args.truncate:
            print("\n" + "=" * 70)
            print("🧹 ОЧИСТКА ТАБЛИЦ")
            print("=" * 70)
            for table in tables_to_process:
                truncate_table(db_manager, table, confirm=not args.force)
        
        elif args.create:
            print("\n" + "=" * 70)
            print("🆕 СОЗДАНИЕ ТАБЛИЦ")
            print("=" * 70)
            for table in tables_to_process:
                create_table(db_manager, table, drop_existing=False)
        
        else:
            print("❌ Укажите действие: --drop, --truncate или --create")
        
        db_manager.close()
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Прервано пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()